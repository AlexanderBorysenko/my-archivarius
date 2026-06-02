"""Tests for the BakeJob document model."""

import pytest
from datetime import datetime

from app.models.bake_job import BakeJob, BakeJobStatus


@pytest.mark.asyncio
class TestBakeJobModel:
    async def test_defaults(self, test_user):
        job = BakeJob(user_id=test_user.id, total_steps=3)
        await job.insert()

        assert job.status == BakeJobStatus.RUNNING
        assert job.total_steps == 3
        assert job.completed_steps == 0
        assert job.current_label is None
        assert job.phase is None
        assert job.entries_created == 0
        assert job.result_entries == []
        assert job.error_message is None
        assert isinstance(job.heartbeat_at, datetime)

    async def test_status_enum_values(self):
        assert BakeJobStatus.RUNNING.value == "running"
        assert BakeJobStatus.COMPLETED.value == "completed"
        assert BakeJobStatus.FAILED.value == "failed"
