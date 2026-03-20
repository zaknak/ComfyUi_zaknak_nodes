import base64
import binascii
import json
import math
import re
import struct
import time
import urllib.error
import urllib.request
import zlib

import torch
import torch.nn.functional as F
import tomli


MASK_BATCH_MODES = ["match_image_batch", "merge_batch_to_one"]
CHAT_COMPLETION_PATH = "/chat/completions"
MODELS_PATH = "/models"
DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
CUSTOM_TYPE_ENDPOINT = "COMPATIBLE_ENDPOINT"


def _normalize_mask_shape(mask: torch.Tensor) -> torch.Tensor:
    if mask.dim() == 2:
        mask = mask.unsqueeze(0)
    if mask.dim() != 3:
        raise ValueError("mask must be [H, W] or [B, H, W]")
    return mask


def _resize_mask(mask: torch.Tensor, height: int, width: int) -> torch.Tensor:
    if mask.shape[1] != height or mask.shape[2] != width:
        mask = F.interpolate(
            mask.unsqueeze(1),
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        ).squeeze(1)
    return mask


def _ensure_batch_mask(
    mask: torch.Tensor,
    batch_size: int,
    height: int,
    width: int,
    mask_batch_mode: str = "match_image_batch",
) -> torch.Tensor:
    mask = _normalize_mask_shape(mask)

    if mask_batch_mode not in MASK_BATCH_MODES:
        raise ValueError(f"unsupported mask_batch_mode: {mask_batch_mode}")

    if mask_batch_mode == "merge_batch_to_one":
        mask = mask.amax(dim=0, keepdim=True)
        mask = _resize_mask(mask, height, width)
        if batch_size > 1:
            mask = mask.expand(batch_size, -1, -1)
        return mask.clamp(0.0, 1.0)

    if mask.shape[0] == 1 and batch_size > 1:
        mask = mask.expand(batch_size, -1, -1)
    elif mask.shape[0] != batch_size:
        raise ValueError("mask batch size must match image batch size")

    mask = _resize_mask(mask, height, width)
    return mask.clamp(0.0, 1.0)


def _gaussian_kernel1d(radius: float, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    sigma = max(float(radius), 1e-6) / 3.0
    kernel_radius = max(1, int(math.ceil(radius)))
    offsets = torch.arange(-kernel_radius, kernel_radius + 1, device=device, dtype=dtype)
    kernel = torch.exp(-(offsets**2) / (2 * sigma * sigma))
    return kernel / kernel.sum()


def _blur_mask(mask: torch.Tensor, radius: float) -> torch.Tensor:
    if radius <= 0:
        return mask.clamp(0.0, 1.0)

    kernel = _gaussian_kernel1d(radius, mask.device, mask.dtype)
    kernel_x = kernel.view(1, 1, 1, -1)
    kernel_y = kernel.view(1, 1, -1, 1)

    blurred = F.conv2d(mask, kernel_x, padding=(0, kernel.numel() // 2))
    blurred = F.conv2d(blurred, kernel_y, padding=(kernel.numel() // 2, 0))
    return blurred.clamp(0.0, 1.0)


def _apply_mosaic(image: torch.Tensor, pixel_size: int) -> torch.Tensor:
    if pixel_size <= 1:
        return image

    _, _, height, width = image.shape
    small_height = max(1, height // pixel_size)
    small_width = max(1, width // pixel_size)
    reduced = F.interpolate(image, size=(small_height, small_width), mode="area")
    return F.interpolate(reduced, size=(height, width), mode="nearest")


def _compute_mask_orientation(mask_2d: torch.Tensor) -> float:
    coords = torch.nonzero(mask_2d > 0.0, as_tuple=False)
    if coords.shape[0] < 2:
        return 0.0

    points = coords[:, [1, 0]].to(dtype=torch.float32)
    centered = points - points.mean(dim=0, keepdim=True)
    covariance = centered.T @ centered / max(points.shape[0] - 1, 1)

    eigenvalues, eigenvectors = torch.linalg.eigh(covariance)
    major = eigenvectors[:, -1]
    major_value = float(eigenvalues[-1].item())
    minor_value = float(eigenvalues[0].item())

    if major_value <= 1e-6:
        return 0.0

    anisotropy = (major_value - minor_value) / max(major_value, 1e-6)
    if anisotropy < 0.15:
        return 0.0

    return math.degrees(math.atan2(float(major[1].item()), float(major[0].item())))


def _build_censor_overlay(
    mask_2d: torch.Tensor,
    angle_deg: float,
    bar_width: float,
    bar_spacing: float,
    width_jitter: float,
    spacing_jitter: float,
    seed: int,
):
    height, width = mask_2d.shape
    coords = torch.nonzero(mask_2d > 0.0, as_tuple=False)
    if coords.numel() == 0:
        return torch.zeros((height, width), device=mask_2d.device, dtype=mask_2d.dtype), {
            "crop_width": 0,
            "crop_height": 0,
        }

    y_coords = coords[:, 0].to(dtype=torch.float32)
    x_coords = coords[:, 1].to(dtype=torch.float32)
    center_x = (float(x_coords.min().item()) + float(x_coords.max().item())) * 0.5
    center_y = (float(y_coords.min().item()) + float(y_coords.max().item())) * 0.5

    angle_rad = math.radians(angle_deg)
    direction = torch.tensor(
        [math.cos(angle_rad), math.sin(angle_rad)],
        device=mask_2d.device,
        dtype=torch.float32,
    )
    normal = torch.tensor([-direction[1], direction[0]], device=mask_2d.device, dtype=torch.float32)

    centered_points = torch.stack((x_coords - center_x, y_coords - center_y), dim=1)
    normal_projection = centered_points @ normal
    extent = float(normal_projection.abs().max().item())

    min_x = int(coords[:, 1].min().item())
    max_x = int(coords[:, 1].max().item())
    min_y = int(coords[:, 0].min().item())
    max_y = int(coords[:, 0].max().item())

    crop_x0 = max(0, min_x)
    crop_x1 = min(width, max_x + 1)
    crop_y0 = max(0, min_y)
    crop_y1 = min(height, max_y + 1)

    crop_width = max(1, crop_x1 - crop_x0)
    crop_height = max(1, crop_y1 - crop_y0)
    crop_half_diagonal = 0.5 * math.hypot(crop_width, crop_height)
    coverage_extent = max(extent + max(float(bar_width), 1.0) + max(float(bar_spacing), 0.0), crop_half_diagonal)

    min_width = 1.0
    min_spacing = 0.0
    generator = torch.Generator(device=mask_2d.device)
    generator.manual_seed(int(seed) & 0x7FFFFFFF)

    bands = []
    position = -coverage_extent
    max_iterations = max(32, int((coverage_extent * 4.0) / max(bar_width + bar_spacing, 1.0)) + 32)
    for _ in range(max_iterations):
        width_noise = (torch.rand(1, generator=generator, device=mask_2d.device).item() * 2.0 - 1.0) * max(width_jitter, 0.0)
        spacing_noise = (torch.rand(1, generator=generator, device=mask_2d.device).item() * 2.0 - 1.0) * max(spacing_jitter, 0.0)
        current_width = max(min_width, float(bar_width) + width_noise)
        current_spacing = max(min_spacing, float(bar_spacing) + spacing_noise)
        bands.append((position, position + current_width))
        position += current_width + current_spacing
        if position > coverage_extent:
            break

    if not bands:
        bands.append((-coverage_extent, coverage_extent))

    projection_min = -coverage_extent
    projection_max = coverage_extent
    projection_length = max(2, int(math.ceil(projection_max - projection_min)) + 3)
    stripe_lookup = torch.zeros(projection_length, device=mask_2d.device, dtype=torch.bool)
    for band_start, band_end in bands:
        start_index = max(0, int(math.floor(band_start - projection_min)))
        end_index = min(projection_length, int(math.ceil(band_end - projection_min)) + 1)
        if end_index > start_index:
            stripe_lookup[start_index:end_index] = True

    crop_yy, crop_xx = torch.meshgrid(
        torch.arange(crop_y0, crop_y1, device=mask_2d.device, dtype=torch.float32),
        torch.arange(crop_x0, crop_x1, device=mask_2d.device, dtype=torch.float32),
        indexing="ij",
    )
    centered_x = crop_xx - center_x
    centered_y = crop_yy - center_y
    pixel_projection = centered_x * normal[0] + centered_y * normal[1]
    projection_index = torch.round(pixel_projection - projection_min).to(dtype=torch.long)
    projection_index.clamp_(0, projection_length - 1)
    crop_overlay = stripe_lookup[projection_index].to(dtype=mask_2d.dtype)

    mask_crop = mask_2d[crop_y0:crop_y1, crop_x0:crop_x1] > 0.0
    crop_overlay = crop_overlay * mask_crop.to(dtype=mask_2d.dtype)

    overlay = torch.zeros((height, width), device=mask_2d.device, dtype=mask_2d.dtype)
    overlay[crop_y0:crop_y1, crop_x0:crop_x1] = crop_overlay
    return overlay, {
        "crop_width": crop_width,
        "crop_height": crop_height,
    }

def _log_timing(stage: str, elapsed: float, details: str = "") -> None:
    suffix = f" | {details}" if details else ""
    print(f"[CensorBarsByMask] {stage}: {elapsed * 1000.0:.2f} ms{suffix}")


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _normalize_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip()
    if not normalized:
        raise ValueError("base_url is required")
    return normalized.rstrip("/")


def _build_api_url(base_url: str, path: str) -> str:
    return f"{_normalize_base_url(base_url)}{path}"


def _build_headers(api_key: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    token = str(api_key or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_json_request(url: str, api_key: str, timeout_seconds: float, payload=None):
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
    request = urllib.request.Request(url=url, data=data, headers=_build_headers(api_key), method=method)
    try:
        with urllib.request.urlopen(request, timeout=max(float(timeout_seconds), 0.1)) as response:
            response_bytes = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed for {url}: {exc.reason}") from exc

    try:
        return json.loads(response_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON response from {url}: {exc}") from exc


def _extract_model_ids(models_response) -> list:
    if isinstance(models_response, dict):
        items = models_response.get("data", models_response.get("models", []))
    else:
        items = models_response

    if not isinstance(items, list):
        return []

    model_ids = []
    for item in items:
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("name")
        else:
            model_id = item
        if isinstance(model_id, str) and model_id.strip():
            model_ids.append(model_id.strip())
    return model_ids


def _extract_model_ids_from_json(models_json: str) -> list:
    text = str(models_json or "").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []

    return _extract_model_ids(parsed)


def _format_model_index_entries(models: list) -> str:
    return "\n".join(f"{index}: {model_name}" for index, model_name in enumerate(models))


def _normalize_endpoint(endpoint: dict, timeout_seconds=None) -> dict:
    if not isinstance(endpoint, dict):
        raise ValueError("endpoint input must be a COMPATIBLE_ENDPOINT object")
    normalized = dict(endpoint)
    normalized["base_url"] = _normalize_base_url(normalized.get("base_url", ""))
    normalized["api_key"] = str(normalized.get("api_key", ""))
    normalized["model_name"] = str(normalized.get("model_name", "")).strip()
    if not normalized["model_name"]:
        raise ValueError("model_name is required on endpoint")
    if timeout_seconds is not None:
        normalized["timeout_seconds"] = float(timeout_seconds)
    else:
        normalized["timeout_seconds"] = float(normalized.get("timeout_seconds", 30.0))
    return normalized


def _coerce_response_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "text" and isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(part for part in parts if part)
    return ""


def _strip_think_tags(text: str) -> str:
    cleaned = str(text or "")
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*?</think>\s*", "", cleaned, flags=re.DOTALL)
    elif "</think>" in cleaned:
        cleaned = re.sub(r"^.*?</think>\s*", "", cleaned, count=1, flags=re.DOTALL)
    return cleaned


def _extract_chat_result(response_json: dict, strip_think_tags: bool = False) -> tuple[str, str, str]:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("response does not contain choices")

    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    text = _coerce_response_text(content)
    if not text and isinstance(first_choice, dict):
        text = _coerce_response_text(first_choice.get("text"))
    if strip_think_tags:
        text = _strip_think_tags(text)
    finish_reason = first_choice.get("finish_reason", "") if isinstance(first_choice, dict) else ""
    usage_json = _json_dumps(response_json.get("usage", {}))
    return text, str(finish_reason or ""), usage_json


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = binascii.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _encode_image_to_png_bytes(image: torch.Tensor) -> bytes:
    if image.dim() != 3:
        raise ValueError("image tensor must be [H, W, C]")
    height, width, channels = image.shape
    if channels < 3:
        raise ValueError("image tensor must have at least 3 channels")

    rgb = image[..., :3].detach().cpu().clamp(0.0, 1.0).mul(255.0).round().to(torch.uint8).contiguous()
    rows = []
    for row_index in range(height):
        row_bytes = bytes(rgb[row_index].reshape(-1).tolist())
        rows.append(b"\x00" + row_bytes)
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", ihdr),
            _png_chunk(b"IDAT", zlib.compress(raw)),
            _png_chunk(b"IEND", b""),
        ]
    )


def _encode_image_to_data_url(image: torch.Tensor) -> str:
    encoded = base64.b64encode(_encode_image_to_png_bytes(image)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


_PROMPT_VARIABLE_PATTERN = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


def _normalize_newlines(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def _validate_preset_path(path: str) -> str:
    file_path = str(path or "").strip()
    if not file_path:
        raise ValueError("preset_path is required")
    if not file_path.lower().endswith(".toml"):
        raise ValueError(f"unsupported extension: preset_path must end with .toml: {file_path}")
    return file_path


def _read_preset_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"file read failed: {path}: {exc}") from exc


def _decode_utf8_text(raw_bytes: bytes, path: str) -> str:
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid utf-8: {path}: {exc}") from exc


def _load_toml_document(path: str) -> dict:
    file_path = _validate_preset_path(path)
    raw_bytes = _read_preset_bytes(file_path)
    text = _decode_utf8_text(raw_bytes, file_path)
    try:
        document = tomli.loads(text)
    except tomli.TOMLDecodeError as exc:
        raise ValueError(f"toml parse error: {file_path}: {exc}") from exc

    if not isinstance(document, dict):
        raise ValueError("invalid preset structure: root document must be a table")
    return document


def _validate_preset_document(document: dict) -> dict:
    version = document.get("version")
    if version != 1:
        raise ValueError(f"unsupported version: expected version = 1, got: {version!r}")

    presets = document.get("presets")
    if not isinstance(presets, dict):
        raise ValueError("invalid preset structure: presets must be a table")
    return presets


def _resolve_preset_definition(document: dict, preset_id: str) -> dict | None:
    target = str(preset_id or "").strip()
    if not target:
        raise ValueError("preset_id is required")

    presets = _validate_preset_document(document)
    preset = presets.get(target)
    if preset is None:
        return None
    if not isinstance(preset, dict):
        raise ValueError(f"invalid preset structure: presets.{target} must be a table")
    if "system" not in preset and "user" not in preset:
        raise ValueError(f"invalid preset structure: presets.{target} must contain system or user")
    return dict(preset)


def _stringify_variable_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return _normalize_newlines(str(value))


def _parse_variables_toml(variables_toml: str) -> dict[str, str]:
    text = str(variables_toml or "").strip()
    if not text:
        return {}

    try:
        variables = tomli.loads(text)
    except tomli.TOMLDecodeError as exc:
        raise ValueError(f"variables_toml parse error: {exc}") from exc
    if not isinstance(variables, dict):
        raise ValueError("variables_toml must decode to a flat key-value table")

    normalized = {}
    for key, value in variables.items():
        if isinstance(value, list):
            raise ValueError(f"variables_toml contains unsupported value type for key '{key}': array")
        if isinstance(value, dict):
            raise ValueError(f"variables_toml contains unsupported value type for key '{key}': table")
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"variables_toml contains unsupported value type for key '{key}': {type(value).__name__}")
        normalized[str(key)] = _stringify_variable_value(value)
    return normalized


def _build_template_variables(input_text: str, variables_toml: str) -> dict[str, str]:
    variables = _parse_variables_toml(variables_toml)
    normalized_input_text = _normalize_newlines(input_text)
    if normalized_input_text:
        variables["input"] = normalized_input_text
    return variables


def _log_unresolved_template_variables(preset_id: str, field_name: str, unresolved_names: list[str]) -> None:
    if not unresolved_names:
        return
    unresolved_text = ", ".join(sorted(set(unresolved_names)))
    print(f"[PromptPreset] unresolved variables in preset '{preset_id}' ({field_name}): {unresolved_text}")


def _render_template(
    text: str,
    variables: dict[str, str],
    keep_unresolved_variables: bool,
    preset_id: str,
    field_name: str,
) -> tuple[str, list[str]]:
    normalized_text = _normalize_newlines(text)
    unresolved_names = []

    def replace(match):
        name = match.group(1)
        if name in variables:
            return variables[name]
        unresolved_names.append(name)
        if keep_unresolved_variables:
            return match.group(0)
        return ""

    rendered = _PROMPT_VARIABLE_PATTERN.sub(replace, normalized_text)
    resolved_unresolved_names = sorted(set(unresolved_names))
    _log_unresolved_template_variables(preset_id, field_name, resolved_unresolved_names)
    return rendered, resolved_unresolved_names


def _build_prompt_outputs(
    preset: dict | None,
    preset_id: str,
    input_text: str,
    variables_toml: str,
    fallback_user_prompt: str,
    keep_unresolved_variables: bool,
) -> tuple[str, str, dict[str, object]]:
    variables = _build_template_variables(input_text, variables_toml)
    fallback = _normalize_newlines(str(fallback_user_prompt or ""))
    prompt_meta = {
        "preset_id": str(preset_id),
        "resolved_variable_names": sorted(variables.keys()),
        "input_text_used": bool(input_text),
        "fallback_used": False,
        "keep_unresolved_variables": bool(keep_unresolved_variables),
        "unresolved_variable_names": [],
        "unresolved_in_system": [],
        "unresolved_in_user": [],
        "unresolved_in_fallback": [],
    }

    if preset is None:
        if fallback:
            prompt_meta["fallback_used"] = True
            rendered_fallback, unresolved_fallback = _render_template(
                fallback,
                variables,
                keep_unresolved_variables,
                str(preset_id),
                "fallback_user_prompt",
            )
            prompt_meta["unresolved_in_fallback"] = unresolved_fallback
            prompt_meta["unresolved_variable_names"] = sorted(set(unresolved_fallback))
            return "", rendered_fallback, prompt_meta
        raise ValueError(f"preset id not found: {preset_id}")

    raw_system = preset.get("system")
    system_prompt = ""
    if raw_system is not None:
        system_prompt, unresolved_system = _render_template(
            str(raw_system),
            variables,
            keep_unresolved_variables,
            str(preset_id),
            "system",
        )
        prompt_meta["unresolved_in_system"] = unresolved_system

    raw_user = preset.get("user")
    if raw_user is None:
        if fallback:
            prompt_meta["fallback_used"] = True
            rendered_fallback, unresolved_fallback = _render_template(
                fallback,
                variables,
                keep_unresolved_variables,
                str(preset_id),
                "fallback_user_prompt",
            )
            prompt_meta["unresolved_in_fallback"] = unresolved_fallback
            prompt_meta["unresolved_variable_names"] = sorted(
                set(prompt_meta["unresolved_in_system"]) | set(unresolved_fallback)
            )
            return system_prompt, rendered_fallback, prompt_meta
        raise ValueError(f"user prompt missing and fallback not available: {preset_id}")

    user_prompt, unresolved_user = _render_template(
        str(raw_user),
        variables,
        keep_unresolved_variables,
        str(preset_id),
        "user",
    )
    prompt_meta["unresolved_in_user"] = unresolved_user
    prompt_meta["unresolved_variable_names"] = sorted(
        set(prompt_meta["unresolved_in_system"]) | set(unresolved_user)
    )
    return system_prompt, user_prompt, prompt_meta


def _build_chat_messages(system_prompt: str, user_prompt: str) -> list:
    messages = []
    if str(system_prompt or ""):
        messages.append({"role": "system", "content": str(system_prompt)})
    if str(user_prompt or ""):
        messages.append({"role": "user", "content": str(user_prompt)})
    if not messages:
        raise ValueError("at least one of system_prompt or user_prompt must be provided")
    return messages


def _build_vision_messages(system_prompt: str, user_prompt: str, image_data_url: str) -> list:
    messages = []
    if str(system_prompt or ""):
        messages.append({"role": "system", "content": str(system_prompt)})

    user_content = []
    if str(user_prompt or ""):
        user_content.append({"type": "text", "text": str(user_prompt)})
    user_content.append(
        {
            "type": "image_url",
            "image_url": {
                "url": image_data_url,
            },
        }
    )
    messages.append({"role": "user", "content": user_content})
    return messages


def _parse_extra_body_json(extra_body_json: str, reserved_keys: set[str]) -> dict:
    text = str(extra_body_json or "").strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"extra_body_json must be valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("extra_body_json must decode to an object")

    collisions = sorted(key for key in parsed.keys() if key in reserved_keys)
    if collisions:
        raise ValueError(f"extra_body_json contains reserved keys: {', '.join(collisions)}")

    return parsed


def _chat_completion_request(
    endpoint: dict,
    messages: list,
    max_tokens: int,
    seed=None,
    extra_body_json="",
    reserved_extra_keys=None,
    strip_think_tags: bool = False,
    strict_finish_reason: bool = True,
):
    payload = {
        "model": endpoint["model_name"],
        "messages": messages,
    }
    if max_tokens > 0:
        payload["max_tokens"] = int(max_tokens)
    if seed is not None:
        payload["seed"] = int(seed)

    extra_body = _parse_extra_body_json(extra_body_json, set(reserved_extra_keys or ()))
    payload.update(extra_body)

    response_json = _http_json_request(
        _build_api_url(endpoint["base_url"], CHAT_COMPLETION_PATH),
        endpoint["api_key"],
        endpoint["timeout_seconds"],
        payload=payload,
    )
    text, finish_reason, usage_json = _extract_chat_result(response_json, strip_think_tags)
    if strict_finish_reason and finish_reason != "stop":
        raise RuntimeError(f"finish_reason must be 'stop', got: {finish_reason!r}")
    return text, _json_dumps(response_json), finish_reason, usage_json

class MosaicByMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "mask_batch_mode": (MASK_BATCH_MODES, {"default": "match_image_batch"}),
                "invert_mask": ("BOOLEAN", {"default": False}),
                "pixel_size": ("INT", {"default": 16, "min": 1, "max": 256, "step": 1}),
                "edge_blur": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 64.0, "step": 0.5}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "apply"
    CATEGORY = "zaknak/image"

    def apply(self, image, mask, mask_batch_mode, invert_mask, pixel_size, edge_blur):
        batch_size, height, width, _ = image.shape
        image_nchw = image.movedim(-1, 1)

        prepared_mask = _ensure_batch_mask(mask, batch_size, height, width, mask_batch_mode)
        if invert_mask:
            prepared_mask = 1.0 - prepared_mask

        final_mask = _blur_mask(prepared_mask.unsqueeze(1), edge_blur)
        mosaic_image = _apply_mosaic(image_nchw, int(pixel_size))
        blended = image_nchw * (1.0 - final_mask) + mosaic_image * final_mask

        return (blended.movedim(1, -1).clamp(0.0, 1.0), final_mask.squeeze(1))


class CensorBarsByMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "mask_batch_mode": (MASK_BATCH_MODES, {"default": "match_image_batch"}),
                "bar_color_r": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "bar_color_g": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "bar_color_b": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "angle_mode": (["manual", "auto"], {"default": "auto"}),
                "angle_deg": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 1.0}),
                "angle_offset_deg": ("FLOAT", {"default": 90.0, "min": -180.0, "max": 180.0, "step": 1.0}),
                "bar_width": ("FLOAT", {"default": 18.0, "min": 1.0, "max": 512.0, "step": 1.0}),
                "bar_spacing": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 512.0, "step": 1.0}),
                "width_jitter": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "spacing_jitter": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "apply"
    CATEGORY = "zaknak/image"

    def apply(
        self,
        image,
        mask,
        mask_batch_mode,
        bar_color_r,
        bar_color_g,
        bar_color_b,
        opacity,
        angle_mode,
        angle_deg,
        angle_offset_deg,
        bar_width,
        bar_spacing,
        width_jitter,
        spacing_jitter,
        seed,
    ):
        total_start = time.perf_counter()
        batch_size, height, width, _ = image.shape
        image_nchw = image.movedim(-1, 1)

        preprocess_start = time.perf_counter()
        prepared_mask = _ensure_batch_mask(mask, batch_size, height, width, mask_batch_mode)
        _log_timing(
            "preprocess_mask",
            time.perf_counter() - preprocess_start,
            f"batch={batch_size}, size={width}x{height}, mode={mask_batch_mode}",
        )

        mask_max = float(prepared_mask.max().item())
        if mask_max <= 0.0 or opacity <= 0.0:
            _log_timing(
                "early_return",
                time.perf_counter() - total_start,
                f"mask_max={mask_max:.4f}, opacity={float(opacity):.2f}",
            )
            return (image.clamp(0.0, 1.0),)

        color_start = time.perf_counter()
        color = torch.tensor(
            [bar_color_r, bar_color_g, bar_color_b],
            device=image.device,
            dtype=image.dtype,
        ).view(1, 3, 1, 1) / 255.0
        _log_timing(
            "prepare_color",
            time.perf_counter() - color_start,
            f"rgb=({bar_color_r},{bar_color_g},{bar_color_b}), opacity={float(opacity):.2f}",
        )

        overlays = []
        for batch_index in range(batch_size):
            batch_start = time.perf_counter()
            current_mask = prepared_mask[batch_index]
            active_pixels = int((current_mask > 0.0).sum().item())
            if active_pixels == 0:
                overlays.append(torch.zeros((height, width), device=image.device, dtype=image.dtype))
                _log_timing(
                    f"batch[{batch_index}]_skip",
                    time.perf_counter() - batch_start,
                    "active_pixels=0",
                )
                continue

            orientation_start = time.perf_counter()
            resolved_angle = float(angle_deg)
            if angle_mode == "auto":
                resolved_angle = _compute_mask_orientation(current_mask)
            resolved_angle += float(angle_offset_deg)
            _log_timing(
                f"batch[{batch_index}]_resolve_angle",
                time.perf_counter() - orientation_start,
                f"mode={angle_mode}, active_pixels={active_pixels}, angle={resolved_angle:.2f}",
            )

            overlay_start = time.perf_counter()
            overlay, overlay_meta = _build_censor_overlay(
                current_mask,
                resolved_angle,
                float(bar_width),
                float(bar_spacing),
                float(width_jitter),
                float(spacing_jitter),
                int(seed) + batch_index,
            )
            overlays.append(overlay)
            _log_timing(
                f"batch[{batch_index}]_build_overlay",
                time.perf_counter() - overlay_start,
                f"width={float(bar_width):.2f}, spacing={float(bar_spacing):.2f}, seed={int(seed) + batch_index}, crop={overlay_meta['crop_width']}x{overlay_meta['crop_height']}",
            )
            _log_timing(
                f"batch[{batch_index}]_total",
                time.perf_counter() - batch_start,
                f"active_pixels={active_pixels}",
            )

        composite_start = time.perf_counter()
        overlay_mask = torch.stack(overlays, dim=0).unsqueeze(1)
        alpha = overlay_mask * float(opacity)
        blended = image_nchw * (1.0 - alpha) + color * alpha
        _log_timing("composite", time.perf_counter() - composite_start, f"batch={batch_size}")
        _log_timing("total", time.perf_counter() - total_start)
        return (blended.movedim(1, -1).clamp(0.0, 1.0),)


class CompatibleEndpoint:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": DEFAULT_BASE_URL}),
                "api_key": ("STRING", {"default": ""}),
                "model_name": ("STRING", {"default": ""}),
                "refresh_models": ("BOOLEAN", {"default": True}),
                "timeout_seconds": ("FLOAT", {"default": 10.0, "min": 0.1, "max": 300.0, "step": 0.5}),
            }
        }

    RETURN_TYPES = (CUSTOM_TYPE_ENDPOINT, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("endpoint", "model_name", "models_json", "status_text")
    FUNCTION = "build"
    CATEGORY = "zaknak/llm"

    def build(self, base_url, api_key, model_name, refresh_models, timeout_seconds):
        normalized_base_url = _normalize_base_url(base_url)
        selected_model = str(model_name or "").strip()
        models_response = {"data": []}
        status_parts = []
        models = []

        if refresh_models:
            try:
                models_response = _http_json_request(
                    _build_api_url(normalized_base_url, MODELS_PATH),
                    str(api_key or ""),
                    float(timeout_seconds),
                    payload=None,
                )
                models = _extract_model_ids(models_response)
                if not selected_model and models:
                    selected_model = models[0]
                    status_parts.append("first fetched model auto-selected")
                status_parts.append(f"models fetched: {len(models)}")
            except Exception as exc:
                models_response = {"error": str(exc), "data": []}
                status_parts.append(f"model fetch failed: {exc}")
        else:
            status_parts.append("model fetch skipped")

        if not selected_model:
            status_parts.append("model_name is empty")
        elif models and selected_model not in models:
            status_parts.append("model_name not found in fetched models")
        else:
            status_parts.append(f"model_name={selected_model}" if selected_model else "")

        endpoint = {
            "base_url": normalized_base_url,
            "api_key": str(api_key or ""),
            "model_name": selected_model,
            "timeout_seconds": float(timeout_seconds),
            "models": models,
        }
        status_text = " | ".join(part for part in status_parts if part)
        return (endpoint, selected_model, _json_dumps(models_response), status_text)

class CompatibleModelSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "models_json": ("STRING", {"default": "", "multiline": True}),
                "model_index": ("INT", {"default": 0, "min": 0, "max": 65535, "step": 1}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("model_name",)
    FUNCTION = "select_model"
    CATEGORY = "zaknak/llm"

    def select_model(self, models_json, model_index):
        models = _extract_model_ids_from_json(models_json)
        index = int(model_index)
        if index < 0 or index >= len(models):
            return ("",)
        return (models[index],)


class CompatibleModelListView:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "models_json": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("models_list_text",)
    FUNCTION = "build_list"
    CATEGORY = "zaknak/llm"

    def build_list(self, models_json):
        models = _extract_model_ids_from_json(models_json)
        return (_format_model_index_entries(models),)


class PromptPreset:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "preset_path": ("STRING", {"default": ""}),
                "preset_id": ("STRING", {"default": ""}),
                "input_text": ("STRING", {"default": "", "multiline": True}),
                "variables_toml": ("STRING", {"default": "", "multiline": True}),
                "fallback_user_prompt": ("STRING", {"default": "", "multiline": True}),
                "keep_unresolved_variables": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "user_prompt", "preset_meta_json", "preset_name")
    FUNCTION = "load_preset"
    CATEGORY = "zaknak/llm"

    def load_preset(self, preset_path, preset_id, input_text, variables_toml, fallback_user_prompt, keep_unresolved_variables):
        document = _load_toml_document(preset_path)
        preset = _resolve_preset_definition(document, preset_id)
        system_prompt, user_prompt, prompt_meta = _build_prompt_outputs(
            preset,
            preset_id,
            input_text,
            variables_toml,
            fallback_user_prompt,
            bool(keep_unresolved_variables),
        )
        preset_name = str((preset or {}).get("label") or preset_id)
        preset_meta = {
            key: value
            for key, value in (preset or {}).items()
            if key not in {"system", "user"}
        }
        preset_meta["_prompt_preset"] = prompt_meta
        return (system_prompt, user_prompt, _json_dumps(preset_meta), preset_name)


class ChatOnce:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "endpoint": (CUSTOM_TYPE_ENDPOINT,),
                "system_prompt": ("STRING", {"default": "", "multiline": True}),
                "user_prompt": ("STRING", {"default": "", "multiline": True}),
                "max_tokens": ("INT", {"default": 10240, "min": 0, "max": 65535, "step": 1}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF, "step": 1}),
                "extra_body_json": ("STRING", {"default": "", "multiline": True}),
                "strict_finish_reason": ("BOOLEAN", {"default": True}),
                "strip_think_tags": ("BOOLEAN", {"default": False}),
                "timeout_seconds": ("FLOAT", {"default": 60.0, "min": 0.1, "max": 300.0, "step": 0.5}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "response_json", "finish_reason", "usage_json")
    FUNCTION = "chat"
    CATEGORY = "zaknak/llm"

    def chat(self, endpoint, system_prompt, user_prompt, max_tokens, seed, extra_body_json, strict_finish_reason, strip_think_tags, timeout_seconds):
        normalized_endpoint = _normalize_endpoint(endpoint, timeout_seconds)
        messages = _build_chat_messages(system_prompt, user_prompt)
        return _chat_completion_request(
            normalized_endpoint,
            messages,
            int(max_tokens),
            int(seed),
            extra_body_json,
            {"model", "messages", "max_tokens", "seed"},
            bool(strip_think_tags),
            bool(strict_finish_reason),
        )


class VisionChatOnce:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "endpoint": (CUSTOM_TYPE_ENDPOINT,),
                "image": ("IMAGE",),
                "system_prompt": ("STRING", {"default": "", "multiline": True}),
                "user_prompt": ("STRING", {"default": "", "multiline": True}),
                "max_tokens": ("INT", {"default": 10240, "min": 0, "max": 65535, "step": 1}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF, "step": 1}),
                "extra_body_json": ("STRING", {"default": "", "multiline": True}),
                "strict_finish_reason": ("BOOLEAN", {"default": True}),
                "strip_think_tags": ("BOOLEAN", {"default": False}),
                "timeout_seconds": ("FLOAT", {"default": 60.0, "min": 0.1, "max": 300.0, "step": 0.5}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "response_json", "finish_reason", "usage_json")
    FUNCTION = "chat"
    CATEGORY = "zaknak/llm"

    def chat(self, endpoint, image, system_prompt, user_prompt, max_tokens, seed, extra_body_json, strict_finish_reason, strip_think_tags, timeout_seconds):
        normalized_endpoint = _normalize_endpoint(endpoint, timeout_seconds)
        if image.shape[0] < 1:
            raise ValueError("image input is empty")
        image_data_url = _encode_image_to_data_url(image[0])
        messages = _build_vision_messages(system_prompt, user_prompt, image_data_url)
        return _chat_completion_request(
            normalized_endpoint,
            messages,
            int(max_tokens),
            int(seed),
            extra_body_json,
            {"model", "messages", "max_tokens", "seed"},
            bool(strip_think_tags),
            bool(strict_finish_reason),
        )


NODE_CLASS_MAPPINGS = {
    "MosaicByMask": MosaicByMask,
    "CensorBarsByMask": CensorBarsByMask,
    "CompatibleEndpoint": CompatibleEndpoint,
    "CompatibleModelListView": CompatibleModelListView,
    "CompatibleModelSelector": CompatibleModelSelector,
    "PromptPreset": PromptPreset,
    "ChatOnce": ChatOnce,
    "VisionChatOnce": VisionChatOnce,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MosaicByMask": "Mosaic By Mask",
    "CensorBarsByMask": "Censor Bars By Mask",
    "CompatibleEndpoint": "Compatible Endpoint",
    "CompatibleModelListView": "Compatible Model List View",
    "CompatibleModelSelector": "Compatible Model Selector",
    "PromptPreset": "Prompt Preset",
    "ChatOnce": "Chat Once",
    "VisionChatOnce": "Vision Chat Once",
}







