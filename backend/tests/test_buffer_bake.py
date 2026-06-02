"""Tests for buffer bake orchestration, guards, and recovery."""

import pytest
from datetime import datetime, timedelta

from bson import ObjectId

from app.models.bake_job import BakeJob, BakeJobStatus


@pytest.mark.asyncio
class TestActiveBakeHelper:
    async def test_returns_running_job(self, test_user):
        from app.api.buffer import _active_bake
        job = BakeJob(user_id=test_user.id, total_steps=2)
        await job.insert()

        active = await _active_bake(test_user.id)
        assert active is not None
        assert active.id == job.id

    async def test_returns_none_when_no_job(self, test_user):
        from app.api.buffer import _active_bake
        assert await _active_bake(test_user.id) is None

    async def test_recovers_stale_job_and_returns_none(self, test_user):
        from app.api.buffer import _active_bake
        job = BakeJob(
            user_id=test_user.id,
            total_steps=2,
            heartbeat_at=datetime.utcnow() - timedelta(seconds=999),
        )
        await job.insert()

        active = await _active_bake(test_user.id)
        assert active is None

        refreshed = await BakeJob.get(job.id)
        assert refreshed.status == BakeJobStatus.FAILED
        assert refreshed.error_message is not None


@pytest.mark.asyncio
class TestFailOrphanedBakes:
    async def test_marks_running_jobs_failed(self, test_user):
        from app.api.buffer import _fail_orphaned_bakes
        running = BakeJob(user_id=test_user.id, total_steps=1)
        await running.insert()
        # Use a distinct user_id for the completed job to avoid the mongomock unique-index
        # limitation (mongomock drops partialFilterExpression, making it a full unique index).
        other_uid = ObjectId()
        done = BakeJob(user_id=other_uid, status=BakeJobStatus.COMPLETED, total_steps=1)
        await done.insert()

        await _fail_orphaned_bakes()

        assert (await BakeJob.get(running.id)).status == BakeJobStatus.FAILED
        assert (await BakeJob.get(done.id)).status == BakeJobStatus.COMPLETED


from unittest.mock import AsyncMock, patch
from app.models.entry import Entry


@pytest.mark.asyncio
class TestRunBake:
    @patch("app.api.buffer.bake_messages", new_callable=AsyncMock)
    async def test_success_marks_completed_and_fills_result(self, mock_bake, test_user):
        from app.api.buffer import _run_bake

        entry = Entry(user_id=test_user.id, date=__import__("datetime").date(2026, 4, 22),
                      content="x" * 300, source_messages=[], version=1)
        await entry.insert()
        mock_bake.return_value = [entry]

        job = BakeJob(user_id=test_user.id, total_steps=1)
        await job.insert()

        await _run_bake(str(job.id), str(test_user.id), test_user.id, [])

        refreshed = await BakeJob.get(job.id)
        assert refreshed.status == BakeJobStatus.COMPLETED
        assert refreshed.completed_steps == refreshed.total_steps
        assert refreshed.entries_created == 1
        assert len(refreshed.result_entries) == 1
        assert len(refreshed.result_entries[0]["preview"]) == 200

    @patch("app.api.buffer.bake_messages", new_callable=AsyncMock)
    async def test_exception_marks_failed(self, mock_bake, test_user):
        from app.api.buffer import _run_bake
        mock_bake.side_effect = RuntimeError("boom")

        job = BakeJob(user_id=test_user.id, total_steps=1)
        await job.insert()

        await _run_bake(str(job.id), str(test_user.id), test_user.id, [])

        refreshed = await BakeJob.get(job.id)
        assert refreshed.status == BakeJobStatus.FAILED
        assert "boom" in refreshed.error_message

    @patch("app.api.buffer.bake_messages", new_callable=AsyncMock)
    async def test_does_not_resurrect_a_recovered_job(self, mock_bake, test_user):
        """If the job was flipped to FAILED (stale recovery / restart) while the
        engine was running, the completion write must NOT revive it to COMPLETED."""
        from app.api.buffer import _run_bake
        from app.models.entry import Entry

        entry = Entry(user_id=test_user.id, date=__import__("datetime").date(2026, 4, 22),
                      content="done", source_messages=[], version=1)
        await entry.insert()

        job = BakeJob(user_id=test_user.id, total_steps=1)
        await job.insert()

        async def flip_then_return(*args, **kwargs):
            # Simulate a concurrent recovery marking the job FAILED mid-bake.
            recovered = await BakeJob.get(job.id)
            recovered.status = BakeJobStatus.FAILED
            recovered.error_message = "stale: no heartbeat"
            await recovered.save()
            return [entry]

        mock_bake.side_effect = flip_then_return

        await _run_bake(str(job.id), str(test_user.id), test_user.id, [])

        refreshed = await BakeJob.get(job.id)
        assert refreshed.status == BakeJobStatus.FAILED  # NOT resurrected to COMPLETED


from fastapi import HTTPException
from app.models.raw_message import RawMessage, SourceType, MessageStatus


@pytest.mark.asyncio
class TestBakeEndpointGuard:
    @patch("app.api.buffer.media_bucket.flush", new_callable=AsyncMock)
    async def test_rejects_when_buffer_empty(self, _flush, test_user):
        from app.api.buffer import bake
        with pytest.raises(HTTPException) as exc:
            await bake(user_id=str(test_user.id))
        assert exc.value.status_code == 422

    @patch("app.api.buffer.media_bucket.flush", new_callable=AsyncMock)
    async def test_rejects_when_bake_already_running(self, _flush, test_user):
        from app.api.buffer import bake
        msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="hi",
            telegram_message_id=1, classified_date=__import__("datetime").date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()
        running = BakeJob(user_id=test_user.id, total_steps=1)
        await running.insert()

        with pytest.raises(HTTPException) as exc:
            await bake(user_id=str(test_user.id))
        assert exc.value.status_code == 409


@pytest.mark.asyncio
class TestGetBufferActiveBake:
    async def test_active_bake_null_when_none(self, test_user):
        from app.api.buffer import get_buffer
        msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="hi",
            telegram_message_id=1, classified_date=__import__("datetime").date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()

        result = await get_buffer(user_id=str(test_user.id))
        assert result["active_bake"] is None
        assert result["can_bake"] is True

    async def test_active_bake_present_blocks_can_bake(self, test_user):
        from app.api.buffer import get_buffer
        msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="hi",
            telegram_message_id=1, classified_date=__import__("datetime").date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()
        running = BakeJob(user_id=test_user.id, total_steps=1, completed_steps=0)
        await running.insert()

        result = await get_buffer(user_id=str(test_user.id))
        assert result["active_bake"] is not None
        assert result["active_bake"]["id"] == str(running.id)
        assert result["can_bake"] is False


@pytest.mark.asyncio
class TestEditLockDuringBake:
    async def test_update_blocked_during_bake(self, test_user):
        from app.api.buffer import update_message, UpdateMessageRequest
        msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="orig",
            telegram_message_id=1, classified_date=__import__("datetime").date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()
        running = BakeJob(user_id=test_user.id, total_steps=1)
        await running.insert()

        with pytest.raises(HTTPException) as exc:
            await update_message(str(msg.id), UpdateMessageRequest(content="new"), user_id=str(test_user.id))
        assert exc.value.status_code == 409

    async def test_delete_blocked_during_bake(self, test_user):
        from app.api.buffer import delete_message
        msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="orig",
            telegram_message_id=1, classified_date=__import__("datetime").date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()
        running = BakeJob(user_id=test_user.id, total_steps=1)
        await running.insert()

        with pytest.raises(HTTPException) as exc:
            await delete_message(str(msg.id), user_id=str(test_user.id))
        assert exc.value.status_code == 409
