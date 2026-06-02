"""Source-agnostic media storage — local disk + owner-scoped resolve."""

import re
import secrets
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.models.media_file import MediaFile

_SHORTCODE_CLEAN = re.compile(r"[^A-Za-z0-9_]")


def allocate_shortcode() -> str:
    """Generate a stable, URL-safe shortcode. Unique index is the backstop."""
    token = _SHORTCODE_CLEAN.sub("", secrets.token_urlsafe(8))
    return f"att_{token}"


def _media_dir() -> Path:
    p = Path(settings.media_files_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_bytes(shortcode: str, data: bytes, ext: str) -> str:
    """Write media bytes to disk; return the absolute path."""
    path = _media_dir() / f"{shortcode}{ext}"
    path.write_bytes(data)
    return str(path)


def save_poster(shortcode: str, data: bytes) -> str:
    """Write a poster/thumbnail; return the absolute path."""
    path = _media_dir() / f"{shortcode}_poster.jpg"
    path.write_bytes(data)
    return str(path)


async def resolve(shortcode: str, user_id: str) -> Optional[MediaFile]:
    """Return the MediaFile only if it exists AND is owned by user_id (no leak)."""
    mf = await MediaFile.find_one({"shortcode": shortcode})
    if not mf or str(mf.user_id) != str(user_id):
        return None
    return mf


async def delete(media_file: MediaFile) -> None:
    """Remove stored files and the document."""
    for key in (media_file.storage_key, media_file.poster_key):
        if key:
            Path(key).unlink(missing_ok=True)
    await media_file.delete()
