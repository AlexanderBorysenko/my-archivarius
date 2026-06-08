"""Web upload → MediaFile ingestion adapter (validate + store, no Telegram)."""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings
from app.core.i18n import t, DEFAULT_LANG
from app.models.media_file import MediaFile, MediaKind, MediaStatus
from app.services.media_storage import allocate_shortcode, save_bytes, save_poster

logger = logging.getLogger(__name__)

_IMAGE_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_VIDEO_MIME_EXT = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}


async def _generate_video_poster(video_path: str) -> bytes | None:
    """Best-effort first-frame poster via ffmpeg. Returns bytes or None on failure."""
    out = f"{video_path}.poster.jpg"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", video_path, "-ss", "0", "-frames:v", "1", out,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return None
        if proc.returncode == 0 and os.path.exists(out):
            return Path(out).read_bytes()
        return None
    except Exception:
        logger.warning("ffmpeg poster generation failed for %s", video_path, exc_info=True)
        return None
    finally:
        Path(out).unlink(missing_ok=True)


async def create_web_media(user_id, data: bytes, content_type: str | None,
                           filename: str | None = None) -> MediaFile:
    """Validate an uploaded blob and persist a READY, attached web MediaFile."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _IMAGE_MIME_EXT:
        kind, ext = MediaKind.PHOTO, _IMAGE_MIME_EXT[ct]
    elif ct in _VIDEO_MIME_EXT:
        kind, ext = MediaKind.VIDEO, _VIDEO_MIME_EXT[ct]
    else:
        raise HTTPException(status_code=415, detail=t("unsupported_file_type", DEFAULT_LANG, ct=ct or '?'))

    if len(data) > settings.media_max_upload_bytes:
        raise HTTPException(status_code=413, detail=t("file_too_large", DEFAULT_LANG))

    shortcode = allocate_shortcode()
    storage_key = save_bytes(shortcode, data, ext)

    poster_key = None
    if kind == MediaKind.VIDEO:
        poster = await _generate_video_poster(storage_key)
        if poster:
            poster_key = save_poster(shortcode, poster)

    mf = MediaFile(
        user_id=user_id,
        shortcode=shortcode,
        kind=kind,
        status=MediaStatus.READY,
        attached=True,
        storage_key=storage_key,
        poster_key=poster_key,
        mime=ct,
        size=len(data),
        source="web",
    )
    await mf.insert()
    return mf
