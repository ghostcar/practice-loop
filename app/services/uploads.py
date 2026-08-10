"""Disk-backed upload storage for user media (inventory photos, photo reports).

Files live under `settings.upload_dir` (Docker: named volume mounted at /app/uploads)
and are served via the `/uploads` static mount in app.main. Only the relative URL
(e.g. `/uploads/inventory/abc123.jpg`) is stored in the DB — the disk stays a detail.
"""

import contextlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
# Magic-byte prefix checks as a second line of defense beyond content_type.
_MAGIC: dict[str, bytes] = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/webp": b"RIFF",
    "image/gif": b"GIF8",
}


def _base_dir() -> Path:
    d = Path(settings.upload_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_image(file: UploadFile, subdir: str = "general") -> str:
    """Validate and persist an uploaded image.

    Returns the public URL path (``/uploads/<subdir>/<uuid>.<ext>``).
    Raises HTTPException(400) on wrong type, empty body, or oversize file.
    """
    content_type = (file.content_type or "").lower()
    ext = ALLOWED_IMAGE_TYPES.get(content_type)
    if not ext:
        raise HTTPException(400, f"Unsupported image type: {content_type or 'unknown'}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(400, f"Image too large (max {settings.max_upload_bytes // (1024 * 1024)} MB)")
    # Magic-byte check (defense in depth against content-type spoofing).
    magic = _MAGIC.get(content_type)
    if magic and not data.startswith(magic):
        raise HTTPException(400, "File content does not match image type")

    rel_dir = Path("uploads") / subdir
    abs_dir = _base_dir() / subdir
    abs_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (abs_dir / name).write_bytes(data)
    return f"/{rel_dir / name}"


def delete_upload(url_path: str | None) -> None:
    """Best-effort removal of a previously stored file by its public URL.

    Hardened against path traversal: the resolved path must stay inside the
    upload directory, otherwise the file is left untouched.
    """
    if not url_path or not url_path.startswith("/uploads/"):
        return
    rel = url_path[len("/uploads/") :]
    base = _base_dir().resolve()
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)):
        return  # traversal attempt — refuse
    if p.is_file():
        with contextlib.suppress(OSError):
            p.unlink()
