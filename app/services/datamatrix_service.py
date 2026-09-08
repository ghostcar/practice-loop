"""GS1 DataMatrix & Honest Sign (Честный Знак) parser service for pharmaceuticals.

Complies with RF Federal Law No. 425-FZ / Decree No. 1556 on mandatory digital labeling (МДЛП).
Parses GS1 Application Identifiers (AIs):
- (01) GTIN (14 digits) -> extracts EAN-13
- (21) Serial number (13 chars)
- (17) Expiration date (YYMMDD -> YYYY-MM-DD)
- (10) Batch / Lot number
- (91) Verification key (4 chars)
- (92) Crypto signature (44 chars)
Decodes 2D barcodes from images using zxingcpp.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# FNC1 / Group Separator
GS = "\x1d"
GS_ALT = "\u001d"


@dataclass
class DataMatrixParseResult:
    raw_code: str
    gtin: str | None = None
    ean13: str | None = None
    serial: str | None = None
    expiry_date: str | None = None  # YYYY-MM-DD
    lot_number: str | None = None
    crypto_key: str | None = None
    crypto_signature: str | None = None
    is_valid_gs1: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_yymmdd(yymmdd: str) -> str | None:
    """Parse YYMMDD date string to YYYY-MM-DD."""
    if len(yymmdd) != 6 or not yymmdd.isdigit():
        return None
    try:
        yy = int(yymmdd[0:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])
        year = 2000 + yy if yy < 70 else 1900 + yy
        if dd == 0:
            # If day is 00, it means the last day of the month
            if mm in (1, 3, 5, 7, 8, 10, 12):
                dd = 31
            elif mm in (4, 6, 9, 11):
                dd = 30
            elif mm == 2:
                is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
                dd = 29 if is_leap else 28
            else:
                return None
        parsed = date(year, mm, dd)
        return parsed.isoformat()
    except (ValueError, OverflowError):
        return None


def parse_gs1_datamatrix(code: str) -> DataMatrixParseResult:
    """Parse a GS1 DataMatrix string into structured medication labeling components.

    Handles:
    - Raw scanner streams with ASCII 29 (\\x1d) separators
    - Human-readable AI bracket format: (01)046...(21)...
    - Standard Russian MDLP Pharma formats:
      01<14 digits>21<13 chars>[GS]91<4 chars>[GS]92<44 chars>
      01<14 digits>17<6 digits>10<lot>[GS]21<serial>...
    """
    if not code:
        return DataMatrixParseResult(raw_code="")

    clean = code.strip()
    result = DataMatrixParseResult(raw_code=clean)

    # 1. Check bracket format: (01)0460...(17)260831(10)LOT123...
    if "(" in clean and ")" in clean:
        tokens = re.findall(r"\((\d{2,4})\)([^()]+)", clean)
        if tokens:
            for ai, val in tokens:
                val = val.strip()
                if ai == "01" and len(val) >= 14:
                    result.gtin = val[:14]
                    if result.gtin.startswith("0") and len(result.gtin) == 14:
                        result.ean13 = result.gtin[1:]
                elif ai == "21":
                    result.serial = val
                elif ai == "17":
                    result.expiry_date = _parse_yymmdd(val[:6])
                elif ai == "10":
                    result.lot_number = val
                elif ai == "91":
                    result.crypto_key = val
                elif ai == "92":
                    result.crypto_signature = val
            result.is_valid_gs1 = bool(result.gtin)
            return result

    # 2. Stream format with GS separators
    # Normalize separators
    stream = clean.replace(GS_ALT, GS)

    # Check if starts with AI 01
    idx = 0
    if stream.startswith("01") and len(stream) >= 16 and stream[2:16].isdigit():
        result.gtin = stream[2:16]
        if result.gtin.startswith("0"):
            result.ean13 = result.gtin[1:]
        result.is_valid_gs1 = True
        idx = 16

        # Parse remaining AIs from stream
        # Split remaining by GS separator
        remainder = stream[idx:]
        chunks = remainder.split(GS)

        for chunk_idx, chunk in enumerate(chunks):
            pos = 0
            while pos < len(chunk):
                # AI 17: Expiry date (fixed 6 digits)
                if chunk[pos:].startswith("17") and len(chunk[pos:]) >= 8 and chunk[pos + 2 : pos + 8].isdigit():
                    result.expiry_date = _parse_yymmdd(chunk[pos + 2 : pos + 8])
                    pos += 8
                    continue

                # AI 21: Serial (fixed 13 in RF Pharma or variable terminated by GS)
                if chunk[pos:].startswith("21"):
                    pos += 2
                    has_crypto_prefix = chunk[pos:].startswith("91") or chunk[pos:].startswith("92")
                    if chunk_idx == 0 and len(chunk) - pos >= 13 and not has_crypto_prefix:
                        # In RF pharma without GS before 91: exactly 13 chars
                        result.serial = chunk[pos : pos + 13]
                        pos += 13
                    else:
                        result.serial = chunk[pos:]
                        pos = len(chunk)
                    continue

                # AI 10: Lot / Batch (variable, terminated by GS)
                if chunk[pos:].startswith("10"):
                    pos += 2
                    result.lot_number = chunk[pos:]
                    pos = len(chunk)
                    continue

                # AI 91: Verification key (fixed 4 chars in RF pharma)
                if chunk[pos:].startswith("91"):
                    pos += 2
                    result.crypto_key = chunk[pos : pos + 4]
                    pos += 4
                    continue

                # AI 92: Crypto signature (fixed 44 chars)
                if chunk[pos:].startswith("92"):
                    pos += 2
                    result.crypto_signature = chunk[pos:]
                    pos = len(chunk)
                    continue

                # Unknown field or non-GS concatenated field
                pos += 1

    elif stream.isdigit() and len(stream) in (13, 14):
        # Plain EAN-13 or GTIN-14
        if len(stream) == 14:
            result.gtin = stream
            result.ean13 = stream[1:] if stream.startswith("0") else None
        else:
            result.ean13 = stream
            result.gtin = f"0{stream}"
        result.is_valid_gs1 = True

    return result


def decode_datamatrix_from_image(image_bytes: bytes) -> list[DataMatrixParseResult]:
    """Decode 2D barcodes (DataMatrix, QR, etc.) from image bytes using zxingcpp.

    Returns a list of parsed results found in the image.
    """
    if not image_bytes:
        return []

    try:
        import zxingcpp
    except ImportError:
        logger.warning("zxingcpp is not installed; barcode scanning is unavailable.")
        return []

    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        logger.warning("Failed to open image for barcode decoding: %s", e)
        return []

    results: list[DataMatrixParseResult] = []

    def _read(im: Image.Image) -> list[Any]:
        try:
            return zxingcpp.read_barcodes(im)
        except Exception as err:
            logger.debug("zxingcpp read error: %s", err)
            return []

    # 1. Direct read
    barcodes = _read(pil_img)

    # 2. If nothing found, try grayscale and auto-contrast
    if not barcodes:
        try:
            gray = pil_img.convert("L")
            barcodes = _read(gray)
        except Exception:
            pass

    # 3. If still nothing and image is very large, downscale slightly
    if not barcodes and (pil_img.width > 2000 or pil_img.height > 2000):
        try:
            scaled = pil_img.copy()
            scaled.thumbnail((1600, 1600))
            barcodes = _read(scaled)
        except Exception:
            pass

    for b in barcodes:
        txt = b.text.strip()
        if txt:
            parsed = parse_gs1_datamatrix(txt)
            results.append(parsed)

    return results
