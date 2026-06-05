"""Channel-pure inbound intake. Builds and dedup-inserts an InboundEvent.

Imports no channel (aiogram/bot) code, so it is unit-testable without aiogram and
reusable by every channel adapter (Telegram today, web later).
"""

import logging
from typing import Any, Optional
from uuid import uuid4

import pymongo.errors

from app.models.inbound_event import InboundEvent, InboundKind, InboundStatus, Initiator

logger = logging.getLogger(__name__)


async def register_inbound_event(
    *,
    channel: str,
    external_id: str,
    user_id,
    kind: InboundKind,
    initiator: Initiator,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[InboundEvent]:
    """Insert a pending InboundEvent, deduped on (channel, external_id).

    Returns the new event on first delivery, or None if this (channel, external_id)
    was already seen — i.e. a channel redelivery the caller must ignore.
    """
    event = InboundEvent(
        event_id=str(uuid4()),
        channel=channel,
        external_id=str(external_id),
        user_id=user_id,
        kind=kind,
        initiator=initiator,
        payload=payload or {},
        status=InboundStatus.PENDING,
    )
    try:
        await event.insert()
    except pymongo.errors.DuplicateKeyError:
        logger.info(
            "Deduped redelivered inbound event (channel=%s, external_id=%s)",
            channel, external_id,
        )
        return None
    return event


async def inflight_inbound_count(user_id) -> int:
    """Count inbound jobs still being ingested/processed (ANY kind).

    Used to block baking a half-ingested buffer: a message still in the queue hasn't
    become a RawMessage yet and would be missed by a bake.
    """
    return await InboundEvent.find(
        {
            "user_id": user_id,
            "status": {"$in": [InboundStatus.PENDING.value, InboundStatus.PROCESSING.value]},
        }
    ).count()


async def inflight_voice_events(user_id) -> list[InboundEvent]:
    """In-flight VOICE jobs — drives the web 'transcribing' indicator."""
    return await InboundEvent.find(
        {
            "user_id": user_id,
            "kind": InboundKind.VOICE.value,
            "status": {"$in": [InboundStatus.PENDING.value, InboundStatus.PROCESSING.value]},
        }
    ).to_list()
