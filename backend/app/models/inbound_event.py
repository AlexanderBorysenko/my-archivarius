from datetime import datetime
from enum import Enum
from typing import Any, Optional

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel


class InboundKind(str, Enum):
    VOICE = "voice"
    MEDIA = "media"
    TEXT = "text"


class InboundStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class Initiator(BaseModel):
    """Channel reply-context. OPAQUE to the worker — pure passthrough."""

    channel: str = "telegram"
    chat_id: Optional[int] = None
    message_id: Optional[int] = None


class InboundEvent(Document):
    """Durable inbound-message job. The in-process queue. Subsumes AudioJob."""

    event_id: str                       # UUID — output-side idempotency key
    channel: str = "telegram"
    external_id: str                    # channel-native id (telegram update_id) — intake dedup
    user_id: PydanticObjectId
    kind: InboundKind
    initiator: Initiator = Field(default_factory=Initiator)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: InboundStatus = InboundStatus.PENDING
    stage: Optional[str] = None         # downloading | transcribing | classifying | ...
    attempts: int = 0
    next_attempt_at: Optional[datetime] = None
    lease_owner: Optional[str] = None
    lease_at: Optional[datetime] = None
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "inbound_events"
        indexes = [
            IndexModel(
                [("channel", ASCENDING), ("external_id", ASCENDING)],
                unique=True,
                name="uniq_channel_external_id",
            ),
            IndexModel(
                [("status", ASCENDING), ("next_attempt_at", ASCENDING)],
                name="worker_poll",
            ),
            IndexModel(
                [("status", ASCENDING), ("lease_at", ASCENDING)],
                name="orphan_sweep",
            ),
        ]
