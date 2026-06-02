"""Telegram → MediaFile ingestion adapter (download + metadata)."""

import logging

from app.core.events import event_bus
from app.models.media_file import MediaFile, MediaKind, MediaStatus
from app.services.media_storage import allocate_shortcode, save_bytes, save_poster
from app.services.telegram_files import download_telegram_file

logger = logging.getLogger(__name__)

TELEGRAM_MAX_DOWNLOAD = 20 * 1024 * 1024  # Bot API getFile limit

_EXT = {MediaKind.PHOTO: ".jpg", MediaKind.VIDEO: ".mp4", MediaKind.VIDEO_NOTE: ".mp4"}


async def build_media_file(message, user_id, kind: MediaKind) -> MediaFile:
    """Extract metadata from a Telegram media message and persist a PENDING MediaFile."""
    poster_fid = None
    if kind == MediaKind.PHOTO:
        ps = message.photo[-1]  # largest size
        file_id, unique = ps.file_id, ps.file_unique_id
        width, height, size = ps.width, ps.height, ps.file_size
        mime, duration = "image/jpeg", None
    elif kind == MediaKind.VIDEO:
        v = message.video
        file_id, unique = v.file_id, v.file_unique_id
        width, height, size = v.width, v.height, v.file_size
        mime, duration = (v.mime_type or "video/mp4"), v.duration
        poster_fid = v.thumbnail.file_id if v.thumbnail else None
    else:  # VIDEO_NOTE
        vn = message.video_note
        file_id, unique = vn.file_id, vn.file_unique_id
        width = height = vn.length
        size, mime, duration = vn.file_size, "video/mp4", vn.duration
        poster_fid = vn.thumbnail.file_id if vn.thumbnail else None

    mf = MediaFile(
        user_id=user_id,
        shortcode=allocate_shortcode(),
        kind=kind,
        status=MediaStatus.PENDING,
        attached=False,
        mime=mime, size=size, width=width, height=height, duration=duration,
        source="telegram",
        source_ref=unique,
        source_file_id=file_id,
        poster_source_file_id=poster_fid,
        source_group_ref=getattr(message, "media_group_id", None),
    )
    await mf.insert()
    return mf


async def process_media_download(mf: MediaFile, bot_token: str) -> None:
    """Download bytes (or poster only if oversize). Uses partial .set() to avoid
    clobbering the `attached` flag if the bucket flushes concurrently."""
    try:
        if mf.size and mf.size > TELEGRAM_MAX_DOWNLOAD:
            updates = {"status": MediaStatus.OVERSIZE}
            if mf.poster_source_file_id:
                try:
                    poster = await download_telegram_file(mf.poster_source_file_id, bot_token)
                    updates["poster_key"] = save_poster(mf.shortcode, poster)
                except Exception:
                    logger.warning("Oversize poster download failed for %s", mf.shortcode)
            await mf.set(updates)
            await event_bus.publish(str(mf.user_id), "buffer:update")
            return

        data = await download_telegram_file(mf.source_file_id, bot_token)
        updates = {
            "storage_key": save_bytes(mf.shortcode, data, _EXT[mf.kind]),
            "status": MediaStatus.READY,
        }
        if mf.poster_source_file_id:
            try:
                poster = await download_telegram_file(mf.poster_source_file_id, bot_token)
                updates["poster_key"] = save_poster(mf.shortcode, poster)
            except Exception:
                logger.warning("Poster download failed for %s", mf.shortcode)
        await mf.set(updates)
        await event_bus.publish(str(mf.user_id), "buffer:update")

    except Exception as exc:
        await mf.set({
            "status": MediaStatus.FAILED,
            "error_message": str(exc)[:500],
            "attempts": (mf.attempts or 0) + 1,
        })
        logger.error("Media download failed for %s: %s", mf.shortcode, exc)
        raise
