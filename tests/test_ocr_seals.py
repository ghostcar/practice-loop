"""OCR seal engine tests (v0.9.1 — ADR-181)."""

import io

from PIL import Image

from app.media.ocr_seals import (
    _extract_tags,
    _preprocess_for_ocr,
    extract_seal_tag_from_photo,
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_test_image(text: str = "TAG-1234", size: tuple[int, int] = (300, 100)) -> bytes:
    """Create a synthetic image with text for OCR testing."""
    from PIL import ImageDraw, ImageFont

    img = Image.new("L", size, color=255)
    draw = ImageDraw.Draw(img)
    # PIL default font (works without ttf files)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((20, 35), text, fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Unit tests ───────────────────────────────────────────────────────────────


def test_preprocess_for_ocr_returns_grayscale():
    """Preprocessing converts any image to grayscale binarized."""
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    result = _preprocess_for_ocr(img)
    assert result.mode == "L"


def test_preprocess_for_ocr_binarizes():
    """Preprocessing produces only black and white pixels."""
    img = Image.new("L", (100, 100), color=128)
    result = _preprocess_for_ocr(img)
    try:
        pixels = list(result.get_flattened_data())
    except AttributeError:
        pixels = list(result.getdata())
    unique = set(pixels)
    assert unique.issubset({0, 255}), f"Expected only 0/255, got {unique}"


def test_extract_tags_from_empty():
    assert _extract_tags("") == []
    assert _extract_tags("no numbers here") == []


def test_extract_tags_finds_patterns():
    result = _extract_tags("Seal TAG-48291 activated\nBackup PL-0001 ok")
    assert "48291" in result
    assert "0001" in result


def test_extract_seal_tag_with_real_ocr():
    """End-to-end: synthetic image → OCR → tag extraction."""
    if not _tesseract_available():
        import pytest

        pytest.skip("tesseract not available")

    img_bytes = _make_test_image("TAG-48291")
    result = extract_seal_tag_from_photo(img_bytes, expected_tag="TAG-48291")
    assert result["status"] == "success"
    assert result["is_match"] is True
    assert result["extracted_tag"] == "48291" or "48291" in (result["extracted_tag"] or "")
    assert result["confidence"] >= 0.90
    assert result["low_confidence"] is False


def test_extract_seal_tag_no_expected():
    """Without expected_tag, just report what's found."""
    if not _tesseract_available():
        import pytest

        pytest.skip("tesseract not available")

    img_bytes = _make_test_image("XYZ-9999")
    result = extract_seal_tag_from_photo(img_bytes)
    assert result["status"] == "success"
    assert result["extracted_tag"] == "9999" or "9999" in (result["extracted_tag"] or "")
    assert result["confidence"] >= 0.85


def test_extract_seal_tag_mismatch():
    """When expected tag not in photo, is_match=False."""
    if not _tesseract_available():
        import pytest

        pytest.skip("tesseract not available")

    img_bytes = _make_test_image("ABC-1111")
    result = extract_seal_tag_from_photo(img_bytes, expected_tag="XYZ-9999")
    assert result["is_match"] is False
    assert result["low_confidence"] is True


def test_extract_seal_tag_no_text():
    """Blank image yields low confidence."""
    img = Image.new("L", (200, 100), color=255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    result = extract_seal_tag_from_photo(buf.getvalue(), expected_tag="TAG-1234")
    assert result["is_match"] is False
    assert result["confidence"] < 0.75


def test_extract_seal_tag_corrupt_bytes():
    """Corrupt image bytes gracefully handled."""
    result = extract_seal_tag_from_photo(b"not an image", expected_tag="TAG-1234")
    assert result["status"] == "success"
    assert result["is_match"] is False
    assert result["confidence"] == 0.0
    assert result["low_confidence"] is True


# ── Helpers ─────────────────────────────────────────────────────────────────


def _tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
