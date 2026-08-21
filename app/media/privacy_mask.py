"""Privacy Masking & Redaction Engine (Blur & Blackout)."""

from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)


def apply_privacy_mask(
    image_bytes: bytes,
    mask_boxes: list[dict[str, Any]],
    default_mode: str = "blur",
) -> bytes:
    """Applies privacy blur or blackout redaction masks to specified bounding boxes.

    mask_boxes format:
    [
        {"x": 100, "y": 50, "w": 200, "h": 150, "mode": "blur"},
        {"x": 300, "y": 200, "w": 120, "h": 80, "mode": "blackout"}
    ]
    """
    if not mask_boxes:
        return image_bytes

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = img.size

        draw = ImageDraw.Draw(img)

        for box in mask_boxes:
            bx = max(0, int(box.get("x", 0)))
            by = max(0, int(box.get("y", 0)))
            bw = max(1, int(box.get("w", 0)))
            bh = max(1, int(box.get("h", 0)))
            mode = box.get("mode", default_mode)

            # Clamp coordinates to image boundaries
            x2 = min(width, bx + bw)
            y2 = min(height, by + bh)

            if bx >= width or by >= height or x2 <= bx or y2 <= by:
                continue

            crop_box = (bx, by, x2, y2)

            if mode == "blackout":
                draw.rectangle(crop_box, fill=(15, 15, 20))
            elif mode == "pixelate":
                # Pixelate region
                cropped = img.crop(crop_box)
                small_w = max(1, (x2 - bx) // 16)
                small_h = max(1, (y2 - by) // 16)
                pixelated = cropped.resize((small_w, small_h), Image.Resampling.NEAREST).resize(
                    (x2 - bx, y2 - by), Image.Resampling.NEAREST
                )
                img.paste(pixelated, (bx, by))
            else:
                # Gaussian Blur region (default)
                cropped = img.crop(crop_box)
                # Strong multi-pass blur
                blurred = cropped.filter(ImageFilter.GaussianBlur(radius=18))
                img.paste(blurred, (bx, by))

        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=90)
        return out_buf.getvalue()

    except Exception as err:
        logger.warning(f"Privacy masking failed, returning original bytes: {err}")
        return image_bytes
