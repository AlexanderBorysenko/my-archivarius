"""Tests for the inbound worker: claim, process, retry, recovery, idempotency."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.models.inbound_event import InboundEvent, InboundKind, InboundStatus, Initiator
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.services import worker


async def _make_voice_event(user_id, external_id="1", audio_ref="/tmp/a.ogg"):
    voice = {"file_id": "FID", "duration": 3.0}
    if audio_ref is not None:
        voice["audio_ref"] = audio_ref
    event = InboundEvent(
        event_id=f"evt-{external_id}",
        external_id=external_id,
        user_id=user_id,
        kind=InboundKind.VOICE,
        initiator=Initiator(channel="telegram", chat_id=1, message_id=2),
        payload={"voice": voice},
        status=InboundStatus.PENDING,
    )
    await event.insert()
    return event


@pytest.mark.asyncio
class TestClaim:
    async def test_claim_marks_processing(self, test_user):
        await _make_voice_event(test_user.id)
        claimed = await worker.claim_one("owner-1")
        assert claimed is not None
        assert claimed.status == InboundStatus.PROCESSING
        assert claimed.lease_owner == "owner-1"

    async def test_claim_returns_none_when_empty(self, test_user):
        assert await worker.claim_one("owner-1") is None

    async def test_claim_skips_future_retry(self, test_user):
        event = await _make_voice_event(test_user.id)
        event.next_attempt_at = datetime.utcnow() + timedelta(hours=1)
        await event.save()
        assert await worker.claim_one("owner-1") is None


@pytest.mark.asyncio
class TestProcess:
    async def test_voice_success_creates_raw_message(self, test_user):
        event = await _make_voice_event(test_user.id)
        claimed = await worker.claim_one("o")
        with patch.object(worker, "transcribe_audio", AsyncMock(return_value="привіт")), \
             patch.object(worker, "classify_date", AsyncMock(return_value=datetime.utcnow().date())), \
             patch.object(worker, "notify_outcome", AsyncMock()) as notify:
            await worker.process_event(claimed)
        refreshed = await InboundEvent.get(event.id)
        assert refreshed.status == InboundStatus.DONE
        rm = await RawMessage.find_one({"event_id": event.event_id})
        assert rm is not None
        assert rm.content == "привіт"
        assert rm.status == MessageStatus.PENDING
        notify.assert_awaited_once()

    async def test_output_idempotent_on_event_id(self, test_user):
        event = await _make_voice_event(test_user.id)
        claimed = await worker.claim_one("o")
        with patch.object(worker, "transcribe_audio", AsyncMock(return_value="x")), \
             patch.object(worker, "classify_date", AsyncMock(return_value=datetime.utcnow().date())), \
             patch.object(worker, "notify_outcome", AsyncMock()):
            await worker.process_event(claimed)
            await worker.process_event(claimed)  # re-run the done job
        assert await RawMessage.find({"event_id": event.event_id}).count() == 1

    async def test_failure_retries_then_errors(self, test_user):
        event = await _make_voice_event(test_user.id)
        claimed = await worker.claim_one("o")
        with patch.object(worker, "transcribe_audio", AsyncMock(side_effect=RuntimeError("boom"))), \
             patch.object(worker, "notify_outcome", AsyncMock()) as notify, \
             patch.object(worker.settings, "worker_max_attempts", 2):
            # First failure -> back to pending with a future next_attempt_at, no user error yet.
            await worker.process_event(claimed)
            after1 = await InboundEvent.get(event.id)
            assert after1.status == InboundStatus.PENDING
            assert after1.attempts == 1
            assert after1.next_attempt_at is not None
            notify.assert_not_awaited()

            # Make the retry due, claim again, fail again -> attempts exhausted -> error + notify.
            after1.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
            await after1.save()
            claimed2 = await worker.claim_one("o")
            assert claimed2 is not None
            await worker.process_event(claimed2)
            after2 = await InboundEvent.get(event.id)
            assert after2.status == InboundStatus.ERROR
            assert after2.attempts == 2
            notify.assert_awaited_once()


@pytest.mark.asyncio
class TestRecovery:
    async def test_requeue_stranded_processing(self, test_user):
        event = await _make_voice_event(test_user.id)
        event.status = InboundStatus.PROCESSING
        event.lease_owner = "dead-worker"
        await event.save()
        n = await worker.requeue_stranded_jobs()
        assert n == 1
        refreshed = await InboundEvent.get(event.id)
        assert refreshed.status == InboundStatus.PENDING
        assert refreshed.lease_owner is None


@pytest.mark.asyncio
class TestVoiceRecoveryDownload:
    async def test_pipeline_downloads_when_ref_missing(self, test_user):
        event = await _make_voice_event(test_user.id, audio_ref=None)
        claimed = await worker.claim_one("o")

        with patch("app.services.transcription.download_voice_to_ref",
                   AsyncMock(return_value="/tmp/recovered.ogg")) as dl, \
             patch.object(worker, "transcribe_audio", AsyncMock(return_value="ok")), \
             patch.object(worker, "classify_date", AsyncMock(return_value=datetime.utcnow().date())), \
             patch.object(worker, "notify_outcome", AsyncMock()):
            await worker.process_event(claimed)

        dl.assert_awaited_once()
        refreshed = await InboundEvent.get(event.id)
        assert refreshed.status == InboundStatus.DONE


@pytest.mark.asyncio
class TestTextPipeline:
    async def test_text_creates_raw_message(self, test_user):
        event = InboundEvent(
            event_id="evt-text-1",
            external_id="9001",
            user_id=test_user.id,
            kind=InboundKind.TEXT,
            initiator=Initiator(channel="telegram", chat_id=1, message_id=2),
            payload={"text": {"content": "сьогодні був гарний день"}},
            status=InboundStatus.PENDING,
        )
        await event.insert()
        claimed = await worker.claim_one("o")

        with patch.object(worker, "classify_date", AsyncMock(return_value=datetime.utcnow().date())), \
             patch.object(worker, "notify_outcome", AsyncMock()):
            await worker.process_event(claimed)

        rm = await RawMessage.find_one({"event_id": "evt-text-1"})
        assert rm is not None
        assert rm.source_type == SourceType.TEXT
        assert rm.content == "сьогодні був гарний день"
