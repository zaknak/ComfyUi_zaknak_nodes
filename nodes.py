import math

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


NODE_CLASS_MAPPINGS = {
    "MosaicByMask": MosaicByMask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MosaicByMask": "Mosaic By Mask",
}
