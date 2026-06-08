"""Buffer API — manage raw messages before baking."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.models.raw_message import RawMessage, MessageStatus, SourceType
from app.models.media_file import MediaFile
from app.models.user import User
from app.services.bake import bake_messages
from app.services.bake_orchestrator import active_bake, serialize_bake_job, launch_bake
from app.services import media_storage
from app.services.media_ingest_web import create_web_media
from app.services.intake import inflight_inbound_count, inflight_voice_events
from app.api.dependencies import get_current_user_id
from app.bot import media_bucket
from app.core.events import event_bus
from app.core.i18n import t, DEFAULT_LANG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/buffer", tags=["Buffer"])


async def _serialize_buffer_message(msg: RawMessage) -> dict:
    data = msg.model_dump(mode="json")
    if msg.source_type == SourceType.MEDIA:
        files = await MediaFile.find(
            {"_id": {"$in": msg.media_file_ids}, "user_id": msg.user_id}
        ).to_list()
        by_id = {f.id: f for f in files}
        ordered = [by_id[mid] for mid in msg.media_file_ids if mid in by_id]
        data["media_files"] = [
            {
                "shortcode": f.shortcode,
                "kind": f.kind.value,
                "status": f.status.value,
                "has_poster": bool(f.poster_key),
            }
            for f in ordered
        ]
    return data


class UpdateMessageRequest(BaseModel):
    content: Optional[str] = None
    classified_date: Optional[date] = None


class UpdateMediaOrderRequest(BaseModel):
    shortcodes: list[str]


async def _get_editable_media_message(message_id: str, user_id: str, lang: str = DEFAULT_LANG) -> RawMessage:
    """Load a pending MEDIA message the user owns and may edit, or raise."""
    msg = await RawMessage.get(message_id)
    if not msg or str(msg.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("msg_not_found", lang))
    if await active_bake(ObjectId(user_id)) is not None:
        raise HTTPException(status_code=409, detail=t("buffer_locked_baking", lang))
    if msg.status == MessageStatus.BAKED:
        raise HTTPException(status_code=400, detail=t("cannot_edit_baked", lang))
    if msg.source_type != SourceType.MEDIA:
        raise HTTPException(status_code=400, detail=t("msg_no_media", lang))
    return msg


@router.get("")
async def get_buffer(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Get all pending messages in the buffer."""
    uid = ObjectId(user_id)
    query = {"user_id": uid, "status": MessageStatus.PENDING}
    if date_from:
        query["classified_date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("classified_date", {})["$lte"] = date_to

    messages = await RawMessage.find(query).sort("+created_at").to_list()

    processing_audio = await inflight_voice_events(uid)

    serialized = list(await asyncio.gather(*(_serialize_buffer_message(m) for m in messages)))

    active = await active_bake(uid)
    inflight = await inflight_inbound_count(uid)

    return {
        "messages": serialized,
        "processing_audio": [ev.model_dump(mode="json") for ev in processing_audio],
        "active_bake": serialize_bake_job(active) if active else None,
        "can_bake": inflight == 0 and active is None and len(messages) > 0,
    }


@router.patch("/{message_id}")
async def update_message(
    message_id: str,
    body: UpdateMessageRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Edit a message in the buffer."""
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    msg = await RawMessage.get(message_id)
    if not msg or str(msg.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("msg_not_found", lang))
    if await active_bake(ObjectId(user_id)) is not None:
        raise HTTPException(status_code=409, detail=t("buffer_locked_baking", lang))
    if msg.status == MessageStatus.BAKED:
        raise HTTPException(status_code=400, detail=t("cannot_edit_baked", lang))

    if body.content is not None:
        msg.content = body.content
    if body.classified_date is not None:
        msg.classified_date = body.classified_date

    await msg.save()
    return msg.model_dump(mode="json")


@router.delete("/{message_id}", status_code=204)
async def delete_message(
    message_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a message from the buffer."""
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    msg = await RawMessage.get(message_id)
    if not msg or str(msg.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("msg_not_found", lang))
    if await active_bake(ObjectId(user_id)) is not None:
        raise HTTPException(status_code=409, detail=t("buffer_locked_baking", lang))
    await msg.delete()
    await event_bus.publish(user_id, "buffer:update")


@router.post("/{message_id}/media/upload")
async def upload_message_media(
    message_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """Upload a new image/video for a media message (not yet ordered into it)."""
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    await _get_editable_media_message(message_id, user_id, lang)
    data = await file.read()
    mf = await create_web_media(ObjectId(user_id), data, file.content_type, file.filename)
    return {
        "shortcode": mf.shortcode,
        "kind": mf.kind.value,
        "status": mf.status.value,
        "has_poster": bool(mf.poster_key),
    }


@router.put("/{message_id}/media")
async def update_message_media(
    message_id: str,
    body: UpdateMediaOrderRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Reconcile a media message to the given ordered shortcode list.

    Rewrites order, deletes removed media, deletes the message if emptied.
    """
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    msg = await _get_editable_media_message(message_id, user_id, lang)
    uid = ObjectId(user_id)

    # The web UI only ever sends shortcodes already in this message plus
    # freshly-uploaded ones; ownership-only resolution below is intentional
    # (a crafted request referencing the user's media from another message is
    # possible but out of scope — owner-only data, no security boundary crossed).
    if len(set(body.shortcodes)) != len(body.shortcodes):
        raise HTTPException(status_code=400, detail=t("duplicate_media", lang))

    files = await MediaFile.find(
        {"shortcode": {"$in": body.shortcodes}, "user_id": uid}
    ).to_list()
    by_code = {f.shortcode: f for f in files}
    missing = [c for c in body.shortcodes if c not in by_code]
    if missing:
        raise HTTPException(status_code=404, detail=t("media_not_found_list", lang, missing=', '.join(missing)))

    new_ids = [by_code[c].id for c in body.shortcodes]
    keep = set(new_ids)
    for mid in msg.media_file_ids:
        if mid not in keep:
            stale = await MediaFile.get(mid)
            if stale:
                await media_storage.delete(stale)

    if not new_ids:
        await msg.delete()
        await event_bus.publish(user_id, "buffer:update")
        return {"deleted": True}

    for f in files:
        if not f.attached:
            await f.set({"attached": True})

    msg.media_file_ids = new_ids
    await msg.save()
    await event_bus.publish(user_id, "buffer:update")
    return await _serialize_buffer_message(msg)


@router.post("/bake", status_code=202)
async def bake(user_id: str = Depends(get_current_user_id)):
    """Start baking pending messages — runs in background, tracked via BakeJob + SSE."""
    uid = ObjectId(user_id)
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG

    # Flush any loose Telegram media so a web-triggered bake doesn't silently drop it.
    await media_bucket.flush(uid, "", datetime.utcnow())

    processing_count = await inflight_inbound_count(uid)
    if processing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=t("api_processing_wait", lang, count=processing_count),
        )

    # Explicit guard (also recovers stale jobs). The partial unique index is
    # the race-proof backstop for truly simultaneous requests.
    if await active_bake(uid) is not None:
        raise HTTPException(status_code=409, detail=t("baking_in_progress", lang))

    pending = await RawMessage.find(
        {"user_id": uid, "status": MessageStatus.PENDING}
    ).sort("+created_at").to_list()
    if not pending:
        raise HTTPException(status_code=422, detail=t("api_buffer_empty", lang))

    total_steps = len({m.classified_date for m in pending})
    try:
        job = await launch_bake(
            uid, user_id, total_steps,
            engine=lambda report: bake_messages(user_id=uid, messages=pending, on_progress=report),
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=t("baking_in_progress", lang))

    return serialize_bake_job(job)
