"""Tests for the InboundEvent durable-queue document."""

import pytest
from datetime import datetime

import pymongo.errors

from app.models.inbound_event import (
    InboundEvent,
    InboundKind,
    InboundStatus,
    Initiator,
)


@pytest.mark.asyncio
class TestInboundEventModel:
    async def test_defaults(self, test_user):
        event = InboundEvent(
            event_id="evt-1",
            external_id="100",
            user_id=test_user.id,
            kind=InboundKind.VOICE,
            initiator=Initiator(channel="telegram", chat_id=5, message_id=7),
        )
        await event.insert()

        assert event.channel == "telegram"
        assert event.status == InboundStatus.PENDING
        assert event.stage is None
        assert event.attempts == 0
        assert event.next_attempt_at is None
        assert event.lease_owner is None
        assert event.payload == {}
        assert event.result == {}
        assert isinstance(event.created_at, datetime)

    async def test_unique_channel_external_id_blocks_redelivery(self, test_user):
        first = InboundEvent(
            event_id="evt-a", external_id="200",
            user_id=test_user.id, kind=InboundKind.VOICE,
        )
        await first.insert()

        dup = InboundEvent(
            event_id="evt-b", external_id="200",  # same (channel, external_id)
            user_id=test_user.id, kind=InboundKind.VOICE,
        )
        with pytest.raises(pymongo.errors.DuplicateKeyError):
            await dup.insert()

    async def test_enum_values(self):
        assert InboundKind.VOICE.value == "voice"
        assert InboundStatus.PROCESSING.value == "processing"
        assert InboundStatus.DONE.value == "done"
