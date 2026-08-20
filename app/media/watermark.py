"""Dynamic Anti-Leak Watermarking Engine for Proof Photos."""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def apply_security_watermark(
    image_bytes: bytes,
    watermark_text: str,
) -> bytes:
    """Overlays semi-transparent security watermark text on proof images."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        txt_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)

        # Position at bottom-left corner
        padding = 15
        x = padding
        y = max(10, image.size[1] - 35)

        # Draw semi-transparent white text with dark outline for contrast
        draw.text((x + 1, y + 1), watermark_text, fill=(0, 0, 0, 180))
        draw.text((x, y), watermark_text, fill=(255, 215, 0, 220))  # Gold color

        watermarked = Image.alpha_composite(image, txt_layer)
        out_buf = io.BytesIO()
        watermarked.convert("RGB").save(out_buf, format="JPEG", quality=90)
        return out_buf.getvalue()
    except Exception as err:
        logger.warning(f"Watermark overlay failed, returning original bytes: {err}")
        return image_bytes
