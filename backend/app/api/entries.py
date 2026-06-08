"""Entries API — diary entries with date navigation."""

from datetime import date, datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.models.entry import Entry
from app.models.raw_message import RawMessage
from app.models.highlight import Highlight
from app.models.media_file import MediaFile
from app.models.user import User
from app.services.blocks import collect_shortcodes, normalize_blocks, blocks_to_text
from app.services.bake import rebake_entry
from app.services.bake_orchestrator import active_bake, launch_bake, serialize_bake_job
from app.api.dependencies import get_current_user_id
from app.core.i18n import t, DEFAULT_LANG

router = APIRouter(prefix="/api/entries", tags=["Entries"])


@router.get("")
async def list_entries(
    page: int = 1,
    per_page: int = 10,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user_id: str = Depends(get_current_user_id),
):
    """List diary entries with pagination, sorted by date (newest first)."""
    uid = ObjectId(user_id)
    query = {"user_id": uid}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})["$lte"] = date_to

    total = await Entry.find(query).count()
    entries = (
        await Entry.find(query)
        .sort("-date")
        .skip((page - 1) * per_page)
        .limit(per_page)
        .to_list()
    )

    all_entries = await Entry.find({"user_id": uid}).sort("-date").to_list()
    available_dates = [e.date.isoformat() for e in all_entries]

    return {
        "items": [_entry_preview(e) for e in entries],
        "total": total,
        "page": page,
        "per_page": per_page,
        "available_dates": available_dates,
    }


@router.get("/by-date/{entry_date}")
async def get_entry_by_date(
    entry_date: date,
    user_id: str = Depends(get_current_user_id),
):
    """Get entry by date with prev/next navigation."""
    uid = ObjectId(user_id)
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    entry = await Entry.find_one({"user_id": uid, "date": entry_date})
    if not entry:
        raise HTTPException(status_code=404, detail=t("entry_not_found_for_date", lang))

    prev_entry = await Entry.find(
        {"user_id": uid, "date": {"$lt": entry_date}}
    ).sort("-date").first_or_none()
    next_entry = await Entry.find(
        {"user_id": uid, "date": {"$gt": entry_date}}
    ).sort("+date").first_or_none()

    highlights = await Highlight.find({"source_entries": entry.id}).to_list()

    return {
        "entry": await _entry_full(entry, highlights, uid),
        "prev_date": prev_entry.date.isoformat() if prev_entry else None,
        "next_date": next_entry.date.isoformat() if next_entry else None,
    }


@router.get("/{entry_id}")
async def get_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a specific entry by ID."""
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("entry_not_found", lang))

    highlights = await Highlight.find({"source_entries": entry.id}).to_list()
    return await _entry_full(entry, highlights, ObjectId(user_id))


@router.get("/{entry_id}/raw")
async def get_entry_raw_messages(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the raw messages that were baked into this entry."""
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("entry_not_found", lang))

    messages = await RawMessage.find(
        {"_id": {"$in": entry.source_messages}}
    ).sort("+created_at").to_list()

    return [msg.model_dump(mode="json") for msg in messages]


@router.post("/{entry_id}/rebake", status_code=202)
async def rebake(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Regenerate an entry from scratch from its own source messages (tracked via BakeJob).

    Replaces the entry's content (discarding manual edits). Shares the bake-job
    concurrency guard, progress, and SSE events with the buffer bake.
    """
    uid = ObjectId(user_id)
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("entry_not_found", lang))
    if not entry.source_messages:
        raise HTTPException(status_code=422, detail=t("no_originals_rebake", lang))
    if await active_bake(uid) is not None:
        raise HTTPException(status_code=409, detail=t("baking_in_progress", lang))

    try:
        job = await launch_bake(
            uid, user_id, total_steps=1,
            engine=lambda report: rebake_entry(uid, entry, report),
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=t("baking_in_progress", lang))

    return serialize_bake_job(job)


class UpdateEntryRequest(BaseModel):
    blocks: list[dict]


@router.patch("/{entry_id}")
async def update_entry(
    entry_id: str,
    body: UpdateEntryRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update an entry's blocks (server-normalized)."""
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("entry_not_found", lang))

    media_files = await MediaFile.find({"user_id": entry.user_id}).to_list()
    media_ctx = {f.shortcode: f.kind.value for f in media_files}
    blocks, _ = normalize_blocks(body.blocks, media_ctx)

    entry.blocks = blocks
    entry.version += 1
    entry.updated_at = datetime.utcnow()
    await entry.save()

    highlights = await Highlight.find({"source_entries": entry.id}).to_list()
    return await _entry_full(entry, highlights, ObjectId(user_id))


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete an entry and its associated highlights."""
    user = await User.get(user_id)
    lang = user.language if user else DEFAULT_LANG
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail=t("entry_not_found", lang))

    await Highlight.find({"source_entries": entry.id}).delete()
    await entry.delete()


async def _media_manifest(blocks, user_id) -> dict:
    shortcodes = collect_shortcodes(blocks)
    if not shortcodes:
        return {}
    files = await MediaFile.find(
        {"user_id": user_id, "shortcode": {"$in": list(shortcodes)}}
    ).to_list()
    return {
        f.shortcode: {
            "kind": f.kind.value,
            "mime": f.mime,
            "width": f.width,
            "height": f.height,
            "status": f.status.value,
            "has_poster": bool(f.poster_key),
        }
        for f in files
    }


def _entry_preview(entry: Entry) -> dict:
    preview = blocks_to_text(entry.blocks)
    return {
        "id": str(entry.id),
        "date": entry.date.isoformat(),
        "content_preview": preview[:200] + "..." if len(preview) > 200 else preview,
        "version": entry.version,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


async def _entry_full(entry: Entry, highlights: list[Highlight], user_id) -> dict:
    return {
        "id": str(entry.id),
        "date": entry.date.isoformat(),
        "blocks": entry.blocks,
        "media": await _media_manifest(entry.blocks, user_id),
        "source_messages_count": len(entry.source_messages),
        "highlights": [
            {"id": str(h.id), "title": h.title, "category": h.category}
            for h in highlights
        ],
        "version": entry.version,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }
