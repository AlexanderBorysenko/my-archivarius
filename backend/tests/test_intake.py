"""Tests for the channel-pure inbound intake / dedup gate."""

import pytest

from app.models.inbound_event import InboundEvent, InboundKind, InboundStatus, Initiator
from app.services.intake import register_inbound_event
from app.services.intake import inflight_inbound_count, inflight_voice_events


@pytest.mark.asyncio
class TestRegisterInboundEvent:
    async def test_first_delivery_creates_event(self, test_user):
        event = await register_inbound_event(
            channel="telegram",
            external_id="500",
            user_id=test_user.id,
            kind=InboundKind.VOICE,
            initiator=Initiator(channel="telegram", chat_id=1, message_id=2),
            payload={"voice": {"file_id": "FID", "duration": 3.0}},
        )

        assert event is not None
        assert event.status == InboundStatus.PENDING
        assert event.event_id  # a UUID was minted
        assert event.payload["voice"]["file_id"] == "FID"
        assert await InboundEvent.find_all().count() == 1

    async def test_redelivery_is_deduped(self, test_user):
        kwargs = dict(
            channel="telegram",
            external_id="501",
            user_id=test_user.id,
            kind=InboundKind.VOICE,
            initiator=Initiator(channel="telegram", chat_id=1, message_id=2),
            payload={"voice": {"file_id": "FID", "duration": 3.0}},
        )
        first = await register_inbound_event(**kwargs)
        second = await register_inbound_event(**kwargs)  # Telegram retry: same external_id

        assert first is not None
        assert second is None  # deduped — caller must do nothing
        assert await InboundEvent.find_all().count() == 1


@pytest.mark.asyncio
class TestInflightHelpers:
    async def _mk(self, user_id, kind, status, ext):
        ev = InboundEvent(
            event_id=f"e-{ext}", external_id=ext, user_id=user_id,
            kind=kind, status=status,
            initiator=Initiator(channel="telegram", chat_id=1, message_id=2),
        )
        await ev.insert()
        return ev

    async def test_counts_all_kinds_pending_and_processing(self, test_user):
        await self._mk(test_user.id, InboundKind.VOICE, InboundStatus.PENDING, "1")
        await self._mk(test_user.id, InboundKind.TEXT, InboundStatus.PROCESSING, "2")
        await self._mk(test_user.id, InboundKind.VOICE, InboundStatus.DONE, "3")  # excluded
        assert await inflight_inbound_count(test_user.id) == 2

    async def test_voice_events_only_voice_inflight(self, test_user):
        await self._mk(test_user.id, InboundKind.VOICE, InboundStatus.PENDING, "1")
        await self._mk(test_user.id, InboundKind.TEXT, InboundStatus.PROCESSING, "2")  # not voice
        await self._mk(test_user.id, InboundKind.VOICE, InboundStatus.DONE, "3")  # done
        voice = await inflight_voice_events(test_user.id)
        assert len(voice) == 1
        assert voice[0].kind == InboundKind.VOICE
