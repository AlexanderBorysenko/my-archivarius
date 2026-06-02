"""Per-user media bucket: accumulate loose files, flush into a MEDIA message.

Also handles album (media_group_id) debounce. Single-process webhook assumption:
per-user asyncio locks + in-memory album aggregation are sufficient.
"""

import asyncio
import logging
from datetime import datetime

from app.core.config import settings
from app.core.events import event_bus
from app.models.media_file import MediaFile, MediaStatus
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.services.classification import classify_date
from app.services.media_ingest_telegram import build_media_file, process_media_download

logger = logging.getLogger(__name__)

ALBUM_DEBOUNCE_SECONDS = 1.5

_user_locks: dict[str, asyncio.Lock] = {}
_albums: dict[tuple, dict] = {}


def _lock_for(user_id) -> asyncio.Lock:
    key = str(user_id)
    if key not in _user_locks:
        _user_locks[key] = asyncio.Lock()
    return _user_locks[key]


async def has_loose_media(user_id) -> bool:
    return await MediaFile.find({"user_id": user_id, "attached": False}).count() > 0


async def flush(user_id, descriptive: str, send_dt: datetime) -> RawMessage | None:
    """Attach all loose media to a new MEDIA message. Returns it, or None if empty."""
    async with _lock_for(user_id):
        loose = await MediaFile.find(
            {"user_id": user_id, "attached": False}
        ).sort("+created_at").to_list()
        if not loose:
            return None

        desc = (descriptive or "").strip()
        if desc:
            try:
                classified = await classify_date(desc, send_dt)
            except Exception:
                classified = send_dt.date()
        else:
            classified = send_dt.date()

        msg = RawMessage(
            user_id=user_id,
            source_type=SourceType.MEDIA,
            content="",
            media_file_ids=[mf.id for mf in loose],
            descriptive=desc or None,
            telegram_message_id=0,
            classified_date=classified,
            status=MessageStatus.PENDING,
        )
        await msg.insert()
        for mf in loose:
            await mf.set({"attached": True})

    await event_bus.publish(str(user_id), "buffer:update")
    return msg


async def ingest_media(user, message, kind) -> None:
    """Entry point from handlers: persist + download the file, then collect/flush."""
    mf = await build_media_file(message, user.id, kind)
    _download_task = asyncio.create_task(process_media_download(mf, settings.telegram_bot_token))
    # retrieve the exception so asyncio doesn't log "task exception was never retrieved"
    # (process_media_download already logs and persists the failure status)
    _download_task.add_done_callback(lambda t: t.exception())

    gid = getattr(message, "media_group_id", None)
    caption = getattr(message, "caption", None)

    if gid is None:
        await _finalize(user, message, caption)
        return

    key = (str(user.id), gid)
    entry = _albums.get(key)
    if entry is None:
        entry = {"caption": None, "message": message, "task": None}
        _albums[key] = entry
    if caption:
        entry["caption"] = caption
    entry["message"] = message
    if entry["task"]:
        entry["task"].cancel()
    entry["task"] = asyncio.create_task(_album_timer(key, user))


async def _album_timer(key, user) -> None:
    try:
        await asyncio.sleep(ALBUM_DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return
    entry = _albums.pop(key, None)
    if entry is None:
        return
    try:
        await _finalize(user, entry["message"], entry["caption"])
    except Exception:
        logger.exception("Album finalize failed for %s", key)


async def _finalize(user, message, caption) -> None:
    """Inline caption flushes the whole bucket; otherwise stay COLLECTING."""
    if caption:
        msg = await flush(user.id, caption, message.date or datetime.utcnow())
        n = len(msg.media_file_ids) if msg else 0
        await message.answer(f"📎 Опис додано до {n} вкладень.")
    else:
        await message.answer("📎 Отримав. Надішли текстовий опис або /skip.")
