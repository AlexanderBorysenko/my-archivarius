"""In-process durable worker for InboundEvent jobs.

Channel-PURE: imports no aiogram / bot code. Hot in-memory handoff for instant pickup
on the happy path, plus a Mongo poll backstop + startup recovery for durability across
restarts. Notification is delegated to the channel-routing notifier.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import settings
from app.core.events import event_bus
from app.models.inbound_event import InboundEvent, InboundKind, InboundStatus
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.services.classification import classify_date
from app.services.transcription import transcribe_audio
from app.services.notifier import notify_outcome

logger = logging.getLogger(__name__)

# Hot-handoff queue: adapters push an event_id; the loop picks it up without poll latency.
_hot_queue: "asyncio.Queue[str]" = asyncio.Queue()

# MEDIA is intentionally absent: media RawMessages are built by media_bucket, not the
# worker (see the MEDIA no-op in process_event).
_KIND_SOURCE = {
    InboundKind.VOICE: SourceType.VOICE,
    InboundKind.TEXT: SourceType.TEXT,
}


def enqueue_hot(event_id: str) -> None:
    """Adapter hook: signal the worker to pick a freshly-inserted job up immediately."""
    _hot_queue.put_nowait(event_id)


def _backoff(attempts: int) -> timedelta:
    """Exponential backoff: 2s, 4s, 8s, ... capped at 5 min."""
    return timedelta(seconds=min(2 ** attempts, 300))


async def claim_one(owner: str) -> Optional[InboundEvent]:
    """Atomically claim the oldest ready pending job via compare-and-swap on status.

    'Ready' = pending AND (no next_attempt_at OR it is due). Returns the claimed
    InboundEvent (status=processing) or None if nothing is claimable.
    """
    now = datetime.utcnow()
    candidates = await InboundEvent.find(
        {
            "status": InboundStatus.PENDING.value,
            "$or": [
                {"next_attempt_at": None},
                {"next_attempt_at": {"$lte": now}},
            ],
        }
    ).sort("+created_at").limit(1).to_list()
    if not candidates:
        return None

    candidate = candidates[0]
    coll = InboundEvent.get_motor_collection()
    res = await coll.update_one(
        {"_id": candidate.id, "status": InboundStatus.PENDING.value},
        {"$set": {
            "status": InboundStatus.PROCESSING.value,
            "lease_owner": owner,
            "lease_at": now,
            "updated_at": now,
        }},
    )
    if res.modified_count != 1:
        return None  # Lost the race to another claim; caller polls again.
    return await InboundEvent.get(candidate.id)


async def _set_stage(event: InboundEvent, stage: str) -> None:
    event.stage = stage
    event.updated_at = datetime.utcnow()
    await event.save()
    await event_bus.publish(str(event.user_id), "buffer:update")


async def _run_pipeline(event: InboundEvent) -> str:
    """Processing dispatch by kind. Returns the buffer text content."""
    if event.kind == InboundKind.VOICE:
        voice = event.payload["voice"]
        audio_ref = voice.get("audio_ref")
        if not audio_ref:
            # Restart recovery: the adapter never finished the download. Redo it here.
            from app.core.config import settings as app_settings
            from app.services.transcription import download_voice_to_ref
            await _set_stage(event, "downloading")
            audio_ref = await download_voice_to_ref(voice["file_id"], app_settings.telegram_bot_token)
            voice["audio_ref"] = audio_ref
            await event.save()
        await _set_stage(event, "transcribing")
        return await transcribe_audio(audio_ref)
    if event.kind == InboundKind.TEXT:
        return event.payload["text"]["content"]
    raise ValueError(f"Worker cannot process kind={event.kind}")


async def process_event(event: InboundEvent) -> None:
    """Run one claimed job: pipeline -> RawMessage (idempotent) -> notify; retry on failure."""
    if event.kind == InboundKind.MEDIA:
        # Media is ingested out-of-band by media_bucket: it creates the MEDIA RawMessage
        # and acks the user directly. The inbound event exists only as an intake-dedup
        # gate, so the worker finalizes it as a no-op — no pipeline, no RawMessage, no
        # notification (that would double-notify). It only ever reaches the worker via the
        # poll backstop, since the media handler never calls enqueue_hot.
        event.status = InboundStatus.DONE
        event.stage = None
        event.updated_at = datetime.utcnow()
        await event.save()
        await event_bus.publish(str(event.user_id), "buffer:update")
        logger.info("Inbound event %s finalized as media no-op (out-of-band ingest)", event.id)
        return
    try:
        content = await _run_pipeline(event)

        await _set_stage(event, "classifying")
        send_dt = event.created_at or datetime.utcnow()
        try:
            classified = await classify_date(content, send_dt)
        except Exception:
            classified = send_dt.date()

        existing = await RawMessage.find_one({"event_id": event.event_id})
        if existing is None:
            raw_msg = RawMessage(
                user_id=event.user_id,
                source_type=_KIND_SOURCE[event.kind],
                content=content,
                telegram_message_id=event.initiator.message_id or 0,
                audio_duration=event.payload.get("voice", {}).get("duration"),
                classified_date=classified,
                status=MessageStatus.PENDING,
                event_id=event.event_id,
            )
            await raw_msg.insert()
            raw_message_id = str(raw_msg.id)
        else:
            raw_message_id = str(existing.id)

        event.status = InboundStatus.DONE
        event.stage = None
        event.result = {"raw_message_id": raw_message_id}
        event.updated_at = datetime.utcnow()
        await event.save()

        await notify_outcome(
            user_id=str(event.user_id),
            initiator=event.initiator,
            ok=True,
            kind=event.kind.value,
        )
        logger.info("Inbound event %s done (kind=%s)", event.id, event.kind.value)

    except Exception as exc:
        event.attempts += 1
        event.error_message = str(exc)[:500]
        event.updated_at = datetime.utcnow()
        if event.attempts < settings.worker_max_attempts:
            event.status = InboundStatus.PENDING
            event.stage = None
            event.lease_owner = None
            event.next_attempt_at = datetime.utcnow() + _backoff(event.attempts)
            await event.save()
            logger.warning("Inbound event %s failed (attempt %d), will retry: %s",
                           event.id, event.attempts, exc)
        else:
            event.status = InboundStatus.ERROR
            event.stage = None
            await event.save()
            logger.error("Inbound event %s errored after %d attempts: %s",
                         event.id, event.attempts, exc)
            await notify_outcome(
                user_id=str(event.user_id),
                initiator=event.initiator,
                ok=False,
                kind=event.kind.value,
                error=str(exc),
            )


async def requeue_stranded_jobs() -> int:
    """Startup recovery: reset every 'processing' job back to 'pending'. Returns the count."""
    stranded = await InboundEvent.find(
        {"status": InboundStatus.PROCESSING.value}
    ).to_list()
    for event in stranded:
        event.status = InboundStatus.PENDING
        event.lease_owner = None
        event.lease_at = None
        event.updated_at = datetime.utcnow()
        await event.save()
    return len(stranded)


async def worker_loop() -> None:
    """Long-running worker task. Hot handoff + Mongo poll backstop, semaphore-bounded.

    NOTE: integration-only (not unit-tested). Unit tests target claim_one / process_event /
    requeue_stranded_jobs directly.
    """
    owner = "worker-main"
    sem = asyncio.Semaphore(settings.worker_concurrency)

    async def _process_with_sem(event: InboundEvent) -> None:
        try:
            await process_event(event)
        finally:
            sem.release()

    logger.info("Inbound worker loop started (owner=%s, concurrency=%d)",
                owner, settings.worker_concurrency)
    while True:
        # Wait for a hot signal, or fall through on the poll timeout (durable backstop).
        try:
            await asyncio.wait_for(_hot_queue.get(), timeout=settings.worker_poll_seconds)
        except asyncio.TimeoutError:
            pass

        # Claim greedily up to the concurrency bound; sem.acquire() throttles in-flight work.
        while True:
            await sem.acquire()
            event = await claim_one(owner)
            if event is None:
                sem.release()
                break
            asyncio.create_task(_process_with_sem(event))
