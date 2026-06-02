from datetime import datetime
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class BakeJobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BakeJob(Document):
    """Tracks a single buffer-baking run — the source of truth for bake progress."""

    user_id: PydanticObjectId
    status: BakeJobStatus = BakeJobStatus.RUNNING
    total_steps: int = 0
    completed_steps: int = 0
    current_label: Optional[str] = None
    phase: Optional[str] = None  # "baking" | "highlights"
    entries_created: int = 0
    result_entries: list[dict] = Field(default_factory=list)
    error_message: Optional[str] = None
    heartbeat_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "bake_jobs"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"status": "running"},
                name="one_running_bake_per_user",
            ),
        ]
