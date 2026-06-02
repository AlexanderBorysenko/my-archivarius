"""Entries API — diary entries with date navigation."""

import re
from datetime import date, datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.models.entry import Entry
from app.models.raw_message import RawMessage
from app.models.highlight import Highlight
from app.models.media_file import MediaFile
from app.api.dependencies import get_current_user_id

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
    entry = await Entry.find_one({"user_id": uid, "date": entry_date})
    if not entry:
        raise HTTPException(status_code=404, detail="Запис за цю дату не знайдено")

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
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    highlights = await Highlight.find({"source_entries": entry.id}).to_list()
    return await _entry_full(entry, highlights, ObjectId(user_id))


@router.get("/{entry_id}/raw")
async def get_entry_raw_messages(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the raw messages that were baked into this entry."""
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    messages = await RawMessage.find(
        {"_id": {"$in": entry.source_messages}}
    ).sort("+created_at").to_list()

    return [msg.model_dump(mode="json") for msg in messages]


class UpdateEntryRequest(BaseModel):
    content: str


@router.patch("/{entry_id}")
async def update_entry(
    entry_id: str,
    body: UpdateEntryRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update an entry's content."""
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    entry.content = body.content
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
    entry = await Entry.get(entry_id)
    if not entry or str(entry.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    await Highlight.find({"source_entries": entry.id}).delete()
    await entry.delete()


async def _media_manifest(content: str, user_id) -> dict:
    shortcodes = set(re.findall(r"attach:([A-Za-z0-9_]+)", content or ""))
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
    return {
        "id": str(entry.id),
        "date": entry.date.isoformat(),
        "content_preview": entry.content[:200] + "..." if len(entry.content) > 200 else entry.content,
        "version": entry.version,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


async def _entry_full(entry: Entry, highlights: list[Highlight], user_id) -> dict:
    return {
        "id": str(entry.id),
        "date": entry.date.isoformat(),
        "content": entry.content,
        "media": await _media_manifest(entry.content, user_id),
        "source_messages_count": len(entry.source_messages),
        "highlights": [
            {"id": str(h.id), "title": h.title, "category": h.category}
            for h in highlights
        ],
        "version": entry.version,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }
