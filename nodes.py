import math
import time

import torch
import torch.nn.functional as F


def _ensure_batch_mask(mask: torch.Tensor, batch_size: int, height: int, width: int) -> torch.Tensor:
    if mask.dim() == 2:
        mask = mask.unsqueeze(0)
    if mask.dim() != 3:
        raise ValueError("mask must be [H, W] or [B, H, W]")

    if mask.shape[0] == 1 and batch_size > 1:
        mask = mask.expand(batch_size, -1, -1)
    elif mask.shape[0] != batch_size:
        raise ValueError("mask batch size must match image batch size")

    if mask.shape[1] != height or mask.shape[2] != width:
        mask = F.interpolate(
            mask.unsqueeze(1),
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        ).squeeze(1)

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


class MosaicByMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "invert_mask": ("BOOLEAN", {"default": False}),
                "pixel_size": ("INT", {"default": 16, "min": 1, "max": 256, "step": 1}),
                "edge_blur": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 64.0, "step": 0.5}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "apply"
    CATEGORY = "zaknak/image"

    def apply(self, image, mask, invert_mask, pixel_size, edge_blur):
        batch_size, height, width, _ = image.shape
        image_nchw = image.movedim(-1, 1)

        prepared_mask = _ensure_batch_mask(mask, batch_size, height, width)
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
        prepared_mask = _ensure_batch_mask(mask, batch_size, height, width)
        _log_timing(
            "preprocess_mask",
            time.perf_counter() - preprocess_start,
            f"batch={batch_size}, size={width}x{height}",
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


NODE_CLASS_MAPPINGS = {
    "MosaicByMask": MosaicByMask,
    "CensorBarsByMask": CensorBarsByMask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MosaicByMask": "Mosaic By Mask",
    "CensorBarsByMask": "Censor Bars By Mask",
}

