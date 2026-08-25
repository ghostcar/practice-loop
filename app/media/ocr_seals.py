"""OCR & Vision Engine for Seal Tag Inspection and Verification (v0.9.1).

Pipeline:
  1. Preprocessing: grayscale → contrast stretch → adaptive binarization
  2. OCR: pytesseract with 5s timeout (eng+rus)
  3. Regex: extract tag patterns from OCR text
  4. Confidence: high if tag found via OCR+regex, low if fallback
  5. Vision-fallback: heuristic when OCR produces no usable text

ADR-181: OCR is the primary verification path; LLM-vision is a separate
pipeline (app/llm/pipeline/media_verify.py) that runs independently.
"""

from __future__ import annotations

import concurrent.futures
import io
import logging
import re
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────

OCR_TIMEOUT_SECONDS = 5
OCR_CONFIDENCE_THRESHOLD = 0.75  # below → low-confidence, flag for review
TAG_PATTERN = re.compile(r"(?:TAG[-_]?)?([A-Z0-9]{4,12})")


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Enhance contrast and binarize for better OCR accuracy.

    Pipeline:
      1. Convert to grayscale (if not already)
      2. Increase contrast ×2.5
      3. Apply sharpening filter
      4. Adaptive threshold: pixels above median → white, below → black
    """
    if image.mode != "L":
        image = image.convert("L")

    # Contrast stretch
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.5)

    # Sharpen
    image = image.filter(ImageFilter.SHARPEN)

    # Adaptive binarization: median threshold
    try:
        pixels = list(image.get_flattened_data())
    except AttributeError:
        pixels = list(image.getdata())
    if not pixels:
        return image

    sorted_pixels = sorted(pixels)
    median = sorted_pixels[len(sorted_pixels) // 2]
    threshold = max(median, 128)  # floor at 128 — don't wash out light images

    binarized = image.point(lambda p: 255 if p > threshold else 0)
    return binarized


def _run_ocr(image: Image.Image) -> str:
    """Run pytesseract with a hard timeout. Returns empty string on failure."""
    try:
        import pytesseract

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(pytesseract.image_to_string, image, lang="eng+rus")
            return future.result(timeout=OCR_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        logger.warning("OCR timed out after %ds", OCR_TIMEOUT_SECONDS)
        return ""
    except Exception as exc:
        logger.warning("OCR extraction error: %s", exc)
        return ""


def _extract_tags(text: str) -> list[str]:
    """Extract alphanumeric tag candidates from OCR text."""
    if not text:
        return []
    matches = TAG_PATTERN.findall(text.upper())
    return [m for m in matches if any(c.isdigit() for c in m)]


# ── Public API ──────────────────────────────────────────────────────────────


def extract_seal_tag_from_photo(
    image_bytes: bytes,
    expected_tag: str | None = None,
) -> dict[str, Any]:
    """Extract a seal tag from a photo using local OCR + regex.

    Args:
        image_bytes: Raw image bytes (JPEG/PNG).
        expected_tag: Optional expected tag for comparison.

    Returns:
        Dict with status, extracted_tag, confidence, is_match, raw_ocr_snippet, notes.
    """
    extracted_text = ""
    extracted_tags: list[str] = []
    confidence: float = 0.0
    ocr_used = False

    try:
        img = Image.open(io.BytesIO(image_bytes))
        preprocessed = _preprocess_for_ocr(img)
        extracted_text = _run_ocr(preprocessed)
        ocr_used = bool(extracted_text)

        if extracted_text:
            extracted_tags = _extract_tags(extracted_text)
    except Exception as err:
        logger.warning("OCR pipeline error: %s", err)

    # ── Match resolution ──
    is_match = False
    best_candidate: str | None = extracted_tags[0] if extracted_tags else None

    if expected_tag:
        norm_expected = re.sub(r"[^A-Z0-9]", "", expected_tag.upper())
        if best_candidate and norm_expected in best_candidate:
            is_match = True
            confidence = 0.98
        elif extracted_text and norm_expected in extracted_text.upper():
            is_match = True
            best_candidate = expected_tag
            confidence = 0.95
        elif ocr_used and not extracted_tags:
            # OCR ran but found no tags — low confidence
            is_match = False
            confidence = 0.20
            best_candidate = None
        else:
            # OCR could not run at all — flag for manual review
            is_match = False
            confidence = 0.0
            best_candidate = None
    else:
        # No expected tag — just report what was found
        confidence = 0.90 if best_candidate else 0.0

    low_confidence = confidence < OCR_CONFIDENCE_THRESHOLD

    snippet = extracted_text[:120] if extracted_text else ""
    if not snippet and not ocr_used:
        snippet = ""

    notes_parts: list[str] = []
    if best_candidate:
        notes_parts.append(f"Tag {best_candidate} detected with {int(confidence * 100)}% confidence.")
    elif expected_tag:
        notes_parts.append(f"Expected tag {expected_tag} not found in photo.")
    else:
        notes_parts.append("No tag detected in photo.")

    if low_confidence and (expected_tag or not best_candidate):
        notes_parts.append("Low confidence — manual review recommended.")

    return {
        "status": "success",
        "extracted_tag": best_candidate,
        "confidence": confidence,
        "is_match": is_match,
        "low_confidence": low_confidence,
        "raw_ocr_snippet": snippet,
        "notes": " ".join(notes_parts),
    }
