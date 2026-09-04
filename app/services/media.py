"""Universal media upload pipeline — platform-level, not tied to LockTimer.

Handles: MIME detection via magic bytes, size limits, SHA-256 hashing,
thumbnail generation (Pillow), safe file naming.

CPU/disk work (Pillow decode, thumbnails, file writes) runs in a thread pool
so the event loop is never blocked (audit P2-2). Pillow's decompression-bomb
guard is enabled so huge images fail closed instead of exhausting memory.

OCR for seal/media verification is implemented in `app.media.ocr_seals`
(ADR-181); HMAC remains the authoritative verification mechanism.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import secrets
import uuid
import warnings
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

from app.config import settings

# ---- Image type allowlist ----

_ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# Magic-byte signatures — defense in depth against content-type spoofing.
_MAGIC: dict[str, bytes] = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/webp": b"RIFF",
    "image/gif": b"GIF8",
}

# ---- Limits ----

MAX_IMAGE_DIMENSION = 12000
THUMBNAIL_MAX_SIZE = (400, 400)

# Pillow decompression-bomb guard (audit P2-2): fail closed on absurd pixel
# counts instead of letting a crafted image exhaust memory. 100 MP is far
# beyond any legitimate photo for this app.
PILLOW_MAX_IMAGE_PIXELS = 100_000_000


def _enable_pillow_guard() -> None:
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = PILLOW_MAX_IMAGE_PIXELS
        # Pillow emits a *warning* on oversized pixel counts; escalate it to an
        # exception so oversized images fail closed instead of exhausting memory.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
    except Exception:
        pass


# Alphabet for verification codes — no ambiguous chars (0/O, 1/I/l).
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------


def _base_dir() -> Path:
    d = Path(settings.upload_dir).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _media_subdir() -> Path:
    sub = _base_dir() / "media"
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def _thumb_subdir() -> Path:
    sub = _base_dir() / "thumbnails"
    sub.mkdir(parents=True, exist_ok=True)
    return sub


async def save_media(file: UploadFile) -> dict:
    """Validate and save a staged media upload.

    Returns a dict with fields for building a MediaAsset row.
    """
    content_type = (file.content_type or "").lower()
    ext = _ALLOWED_MIME.get(content_type)
    if not ext:
        raise HTTPException(400, f"Unsupported media type: {content_type or 'unknown'}")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > settings.media_max_upload_bytes:
        raise HTTPException(
            400,
            f"File too large (max {settings.media_max_upload_bytes // (1024 * 1024)} MB)",
        )

    # Magic-byte check
    magic = _MAGIC.get(content_type)
    if magic and not data.startswith(magic):
        raise HTTPException(400, "File content does not match declared type")

    # SHA-256
    sha256 = hashlib.sha256(data).hexdigest()

    # Disk write + Pillow work is CPU/blocking — run in the thread pool so the
    # event loop stays responsive under concurrent uploads (audit P2-2).
    name = f"{uuid.uuid4().hex}{ext}"
    info = await asyncio.to_thread(_persist_media, data, content_type, name, sha256, file)
    return info


def _persist_media(data: bytes, mime: str, name: str, sha256: str, file: UploadFile) -> dict:
    """Synchronous disk+Pillow pipeline with EXIF/GPS stripping, executed inside thread pool."""
    from app.media.sanitizer import strip_exif_metadata

    clean_data, _ = strip_exif_metadata(data, mime)
    clean_sha256 = hashlib.sha256(clean_data).hexdigest()

    file_path = _media_subdir() / name
    file_path.write_bytes(clean_data)

    width, height = _get_dimensions(clean_data, mime)
    thumb_name = None
    if width and height:
        thumb_name = _make_thumbnail(clean_data, name, mime)

    return {
        "file_path": f"/uploads/media/{name}",
        "thumbnail_path": f"/uploads/thumbnails/{thumb_name}" if thumb_name else None,
        "original_filename": (file.filename or "")[:500] or None,
        "mime_type": mime,
        "file_size_bytes": len(clean_data),
        "sha256_hex": clean_sha256,
        "width": width,
        "height": height,
    }


def _get_dimensions(data: bytes, mime: str) -> tuple[int | None, int | None]:
    """Extract dimensions from image bytes using Pillow (best-effort)."""
    _enable_pillow_guard()
    try:
        from io import BytesIO

        with Image.open(BytesIO(data)) as img:
            w, h = img.size
            if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                raise HTTPException(400, f"Image dimensions exceed {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}")
            return w, h
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):  # type: ignore[attr-defined]
        raise HTTPException(400, "Image is too large (decompression bomb guard)") from None
    except Exception:
        return None, None


def _make_thumbnail(data: bytes, original_name: str, mime: str) -> str | None:
    """Create a thumbnail and return its relative URL path, or None on failure."""
    _enable_pillow_guard()
    try:
        from io import BytesIO

        with Image.open(BytesIO(data)) as img:
            img.thumbnail(THUMBNAIL_MAX_SIZE, Image.LANCZOS)
            thumb_name = f"thumb_{original_name}"
            thumb_path = _thumb_subdir() / thumb_name

            # Save as JPEG for thumbnails (smaller, universal support)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=80)
            return f"/uploads/thumbnails/{thumb_name}"
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):  # type: ignore[attr-defined]
        return None
    except Exception:
        return None


def delete_media_file(file_path: str | None, thumbnail_path: str | None = None) -> None:
    """Best-effort deletion of media and thumbnail files (hardened)."""
    for url in (file_path, thumbnail_path):
        if not url or not url.startswith("/uploads/"):
            continue
        rel = url[len("/uploads/") :]
        base = _base_dir()
        p = (base / rel).resolve()
        if not str(p).startswith(str(base)):
            continue  # traversal attempt
        if p.is_file():
            with contextlib.suppress(OSError):
                p.unlink()


# ---------------------------------------------------------------------------
# Verification challenge helpers
# ---------------------------------------------------------------------------


def generate_verification_code(length: int = 7) -> str:
    """Generate a random alphanumeric code without ambiguous characters."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def compute_code_hmac(code: str) -> str:
    """Compute HMAC-SHA256 of a verification code using CHALLENGE_HMAC_KEY.

    There is no fallback key (audit P0-2): an empty key fails closed instead of
    silently signing with a publicly known constant. In production the key is
    validated at startup by the settings gate.
    """
    key = settings.challenge_hmac_key
    if not key:
        raise RuntimeError("CHALLENGE_HMAC_KEY is not configured")
    return hmac.new(key.encode(), code.encode(), hashlib.sha256).hexdigest()


def verify_code_constant_time(candidate: str, stored_hmac: str) -> bool:
    """Constant-time comparison of HMACs to prevent timing attacks."""
    computed = compute_code_hmac(candidate)
    return hmac.compare_digest(computed, stored_hmac)
