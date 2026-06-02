from datetime import date, datetime
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class SourceType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    MEDIA = "media"


class MessageStatus(str, Enum):
    PENDING = "pending"
    BAKED = "baked"


class RawMessage(Document):
    """A single raw message in the buffer, waiting to be baked into an entry."""

    user_id: PydanticObjectId
    source_type: SourceType
    content: str = ""
    media_file_ids: list[PydanticObjectId] = Field(default_factory=list)
    descriptive: Optional[str] = None
    telegram_message_id: int
    audio_duration: Optional[float] = None
    classified_date: date
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "raw_messages"
