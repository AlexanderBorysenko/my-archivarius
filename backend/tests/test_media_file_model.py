"""Tests for the MediaFile model."""

import pytest

from app.models.media_file import MediaFile, MediaKind, MediaStatus


@pytest.mark.asyncio
class TestMediaFileModel:
    async def test_defaults(self, test_user):
        mf = MediaFile(
            user_id=test_user.id,
            shortcode="att_test123",
            kind=MediaKind.PHOTO,
        )
        await mf.insert()

        fetched = await MediaFile.get(mf.id)
        assert fetched.status == MediaStatus.PENDING
        assert fetched.attached is False
        assert fetched.source == "telegram"
        assert fetched.storage_key is None

    async def test_find_loose(self, test_user):
        loose = MediaFile(user_id=test_user.id, shortcode="att_a", kind=MediaKind.PHOTO)
        attached = MediaFile(
            user_id=test_user.id, shortcode="att_b", kind=MediaKind.PHOTO, attached=True
        )
        await loose.insert()
        await attached.insert()

        result = await MediaFile.find(
            {"user_id": test_user.id, "attached": False}
        ).to_list()
        assert len(result) == 1
        assert result[0].shortcode == "att_a"


from app.models.raw_message import RawMessage, SourceType, MessageStatus
from datetime import date


@pytest.mark.asyncio
class TestRawMessageMedia:
    async def test_media_message(self, test_user):
        msg = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.MEDIA,
            media_file_ids=[],
            descriptive="ранкова пробіжка",
            telegram_message_id=0,
            classified_date=date(2026, 6, 2),
            status=MessageStatus.PENDING,
        )
        await msg.insert()

        fetched = await RawMessage.get(msg.id)
        assert fetched.source_type == SourceType.MEDIA
        assert fetched.content == ""
        assert fetched.descriptive == "ранкова пробіжка"
        assert fetched.media_file_ids == []
