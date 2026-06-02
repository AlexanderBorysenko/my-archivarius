from datetime import datetime
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class MediaKind(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"


class MediaStatus(str, Enum):
    PENDING = "pending"     # created, download in flight
    READY = "ready"         # bytes stored
    OVERSIZE = "oversize"   # too large to download; poster only
    FAILED = "failed"       # download failed


class MediaFile(Document):
    """A source-agnostic, owner-protected media asset."""

    user_id: PydanticObjectId
    shortcode: str
    kind: MediaKind
    status: MediaStatus = MediaStatus.PENDING
    attached: bool = False  # False => still in the bucket

    storage_key: Optional[str] = None       # local path to bytes
    poster_key: Optional[str] = None        # local path to poster/thumbnail

    mime: Optional[str] = None
    size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None

    source: str = "telegram"
    source_ref: Optional[str] = None             # telegram file_unique_id
    source_file_id: Optional[str] = None         # telegram file_id (download)
    poster_source_file_id: Optional[str] = None  # telegram thumbnail file_id
    source_group_ref: Optional[str] = None       # telegram media_group_id

    error_message: Optional[str] = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "media_files"
        indexes = [
            "shortcode",
            [("user_id", 1), ("attached", 1), ("status", 1)],
        ]
