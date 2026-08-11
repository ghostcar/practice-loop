"""Universal media upload pipeline — platform-level, not tied to LockTimer.

Handles: MIME detection via magic bytes, size limits, SHA-256 hashing,
thumbnail generation (Pillow), safe file naming.

OCR support deferred — verification remains HMAC-based only for now.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import secrets
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

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

    # Save original
    name = f"{uuid.uuid4().hex}{ext}"
    file_path = _media_subdir() / name
    file_path.write_bytes(data)

    # Dimensions + thumbnail
    width, height = _get_dimensions(data, content_type)
    thumb_name = None
    if width and height:
        thumb_name = _make_thumbnail(data, name, content_type)

    return {
        "file_path": f"/uploads/media/{name}",
        "thumbnail_path": f"/uploads/thumbnails/{thumb_name}" if thumb_name else None,
        "original_filename": (file.filename or "")[:500] or None,
        "mime_type": content_type,
        "file_size_bytes": len(data),
        "sha256_hex": sha256,
        "width": width,
        "height": height,
    }


def _get_dimensions(data: bytes, mime: str) -> tuple[int | None, int | None]:
    """Extract dimensions from image bytes using Pillow (best-effort)."""
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as img:
            w, h = img.size
            if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                raise HTTPException(400, f"Image dimensions exceed {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}")
            return w, h
    except HTTPException:
        raise
    except Exception:
        return None, None


def _make_thumbnail(data: bytes, original_name: str, mime: str) -> str | None:
    """Create a thumbnail and return its relative URL path, or None on failure."""
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as img:
            img.thumbnail(THUMBNAIL_MAX_SIZE, Image.LANCZOS)
            thumb_name = f"thumb_{original_name}"
            thumb_path = _thumb_subdir() / thumb_name

            # Save as JPEG for thumbnails (smaller, universal support)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=80)
            return f"/uploads/thumbnails/{thumb_name}"
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
    """Compute HMAC-SHA256 of a verification code using CHALLENGE_HMAC_KEY."""
    key = settings.challenge_hmac_key.encode() if settings.challenge_hmac_key else b"default-challenge-key"
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def verify_code_constant_time(candidate: str, stored_hmac: str) -> bool:
    """Constant-time comparison of HMACs to prevent timing attacks."""
    computed = compute_code_hmac(candidate)
    return hmac.compare_digest(computed, stored_hmac)
