"""Buffer API — manage raw messages before baking."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timedelta
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from beanie.operators import Set

from app.models.raw_message import RawMessage, MessageStatus, SourceType
from app.models.audio_job import AudioJob, AudioJobStatus
from app.models.media_file import MediaFile
from app.models.bake_job import BakeJob, BakeJobStatus
from app.services.bake import bake_messages
from app.api.dependencies import get_current_user_id
from app.bot import media_bucket
from app.core.events import event_bus
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/buffer", tags=["Buffer"])


async def _serialize_buffer_message(msg: RawMessage) -> dict:
    data = msg.model_dump(mode="json")
    if msg.source_type == SourceType.MEDIA:
        files = await MediaFile.find(
            {"_id": {"$in": msg.media_file_ids}, "user_id": msg.user_id}
        ).to_list()
        data["media_files"] = [
            {
                "shortcode": f.shortcode,
                "kind": f.kind.value,
                "status": f.status.value,
                "has_poster": bool(f.poster_key),
            }
            for f in files
        ]
    return data


def _serialize_bake_job(job: BakeJob) -> dict:
    return {
        "id": str(job.id),
        "status": job.status.value,
        "total_steps": job.total_steps,
        "completed_steps": job.completed_steps,
        "current_label": job.current_label,
        "phase": job.phase,
        "started_at": job.created_at.isoformat(),
    }


async def _active_bake(uid: ObjectId) -> Optional[BakeJob]:
    """Return the user's current running bake, or None.

    A running job whose heartbeat is older than `bake_stale_seconds` is treated
    as orphaned: it is marked FAILED and None is returned, so a new bake can start.
    """
    job = await BakeJob.find_one(
        {"user_id": uid, "status": BakeJobStatus.RUNNING}
    )
    if job is None:
        return None

    cutoff = datetime.utcnow() - timedelta(seconds=settings.bake_stale_seconds)
    if job.heartbeat_at < cutoff:
        job.status = BakeJobStatus.FAILED
        job.error_message = "stale: no heartbeat"
        job.updated_at = datetime.utcnow()
        await job.save()
        return None

    return job


async def _fail_orphaned_bakes() -> int:
    """Mark every still-running bake job FAILED. Called on app startup so a
    restart mid-bake never leaves a permanent lock. Returns the count recovered."""
    jobs = await BakeJob.find(
        {"status": BakeJobStatus.RUNNING}
    ).to_list()
    for job in jobs:
        job.status = BakeJobStatus.FAILED
        job.error_message = "interrupted by restart"
        job.updated_at = datetime.utcnow()
        await job.save()
    return len(jobs)


class UpdateMessageRequest(BaseModel):
    content: Optional[str] = None
    classified_date: Optional[date] = None


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

    processing_statuses = [AudioJobStatus.PENDING, AudioJobStatus.DOWNLOADING, AudioJobStatus.TRANSCRIBING]
    processing_audio = await AudioJob.find(
        {"user_id": uid, "status": {"$in": processing_statuses}}
    ).to_list()

    serialized = list(await asyncio.gather(*(_serialize_buffer_message(m) for m in messages)))

    active = await _active_bake(uid)

    return {
        "messages": serialized,
        "processing_audio": [job.model_dump(mode="json") for job in processing_audio],
        "active_bake": _serialize_bake_job(active) if active else None,
        "can_bake": len(processing_audio) == 0 and active is None and len(messages) > 0,
    }


@router.patch("/{message_id}")
async def update_message(
    message_id: str,
    body: UpdateMessageRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Edit a message in the buffer."""
    msg = await RawMessage.get(message_id)
    if not msg or str(msg.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Повідомлення не знайдено")
    if await _active_bake(ObjectId(user_id)) is not None:
        raise HTTPException(status_code=409, detail="Не можна змінювати буфер під час запікання")
    if msg.status == MessageStatus.BAKED:
        raise HTTPException(status_code=400, detail="Не можна редагувати вже запечене повідомлення")

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
    msg = await RawMessage.get(message_id)
    if not msg or str(msg.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Повідомлення не знайдено")
    if await _active_bake(ObjectId(user_id)) is not None:
        raise HTTPException(status_code=409, detail="Не можна змінювати буфер під час запікання")
    await msg.delete()
    await event_bus.publish(user_id, "buffer:update")


@router.post("/bake", status_code=202)
async def bake(user_id: str = Depends(get_current_user_id)):
    """Start baking pending messages — runs in background, tracked via BakeJob + SSE."""
    uid = ObjectId(user_id)

    # Flush any loose Telegram media so a web-triggered bake doesn't silently drop it.
    await media_bucket.flush(uid, "", datetime.utcnow())

    processing_statuses = [AudioJobStatus.DOWNLOADING, AudioJobStatus.TRANSCRIBING]
    processing_count = await AudioJob.find(
        {"user_id": uid, "status": {"$in": processing_statuses}}
    ).count()
    if processing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Є {processing_count} повідомлень в процесі транскрибації. Зачекайте завершення.",
        )

    # Explicit guard (also recovers stale jobs). The partial unique index is
    # the race-proof backstop for truly simultaneous requests.
    if await _active_bake(uid) is not None:
        raise HTTPException(status_code=409, detail="Запікання вже виконується")

    pending = await RawMessage.find(
        {"user_id": uid, "status": MessageStatus.PENDING}
    ).sort("+created_at").to_list()
    if not pending:
        raise HTTPException(status_code=422, detail="Буфер порожній — нічого запікати")

    total_steps = len({m.classified_date for m in pending})
    job = BakeJob(user_id=uid, total_steps=total_steps)
    try:
        await job.insert()
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Запікання вже виконується")

    asyncio.create_task(_run_bake(str(job.id), user_id, uid, pending))
    await event_bus.publish(user_id, "bake:started", _serialize_bake_job(job))
    return _serialize_bake_job(job)


async def _run_bake(job_id: str, user_id: str, uid: ObjectId, pending: list):
    """Background bake task — owns the BakeJob, reports progress, publishes via SSE.

    A heartbeat ticker refreshes ``heartbeat_at`` on a fixed interval for the
    whole run, so a long-but-healthy bake (e.g. a slow highlights phase that
    makes many sequential Claude calls) is never mistaken for a dead one by
    ``_active_bake``'s stale-timeout. All terminal writes are guarded on the job
    still being RUNNING, so a job that was already recovered (stale or restart)
    is never silently resurrected.
    """
    oid = ObjectId(job_id)
    job = await BakeJob.get(oid)
    if job is None:
        logger.error("Bake job %s vanished before run", job_id)
        return

    async def report(completed: int, total: int, label: str, phase: str):
        await BakeJob.find_one({"_id": oid, "status": BakeJobStatus.RUNNING}).update(
            Set({
                "completed_steps": completed,
                "total_steps": total,
                "current_label": label,
                "phase": phase,
                "heartbeat_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })
        )
        await event_bus.publish(user_id, "bake:progress", {
            "completed": completed, "total": total, "label": label, "phase": phase,
        })

    heartbeat_interval = max(10, settings.bake_stale_seconds // 5)

    async def heartbeat_ticker():
        """Keep heartbeat_at fresh while the bake runs, independent of phase length."""
        try:
            while True:
                await asyncio.sleep(heartbeat_interval)
                await BakeJob.find_one({"_id": oid, "status": BakeJobStatus.RUNNING}).update(
                    Set({"heartbeat_at": datetime.utcnow()})
                )
        except asyncio.CancelledError:
            pass

    ticker = asyncio.create_task(heartbeat_ticker())
    try:
        logger.info("Bake started for user %s (%d messages)", user_id, len(pending))
        entries = await bake_messages(user_id=uid, messages=pending, on_progress=report)
        logger.info("Bake completed for user %s: %d entries created", user_id, len(entries))

        result_entries = [
            {"id": str(e.id), "date": e.date.isoformat(), "preview": e.content[:200]}
            for e in entries
        ]

        fresh = await BakeJob.get(oid)
        if fresh is None or fresh.status != BakeJobStatus.RUNNING:
            logger.warning(
                "Bake job %s no longer RUNNING at completion (status=%s); skipping completion write",
                job_id, getattr(fresh, "status", None),
            )
            return

        fresh.status = BakeJobStatus.COMPLETED
        fresh.completed_steps = fresh.total_steps
        fresh.entries_created = len(entries)
        fresh.result_entries = result_entries
        fresh.phase = None
        fresh.current_label = None
        fresh.heartbeat_at = datetime.utcnow()
        fresh.updated_at = datetime.utcnow()
        await fresh.save()

        await event_bus.publish(user_id, "bake:complete", {
            "entries_created": len(entries),
            "entries": result_entries,
        })
    except Exception as exc:
        logger.exception("Bake failed for user %s: %s", user_id, exc)
        fresh = await BakeJob.get(oid)
        if fresh is not None and fresh.status == BakeJobStatus.RUNNING:
            fresh.status = BakeJobStatus.FAILED
            fresh.error_message = str(exc)[:300]
            fresh.updated_at = datetime.utcnow()
            await fresh.save()
        try:
            await event_bus.publish(user_id, "bake:error", {"detail": str(exc)[:300]})
        except Exception:
            logger.exception("Failed to publish bake:error event")
    finally:
        ticker.cancel()
        await asyncio.gather(ticker, return_exceptions=True)
