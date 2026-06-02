"""Tests for the media bucket / flush logic."""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

from app.models.media_file import MediaFile, MediaKind
from app.models.raw_message import RawMessage, SourceType
from app.bot import media_bucket


async def _loose(user_id, code):
    mf = MediaFile(user_id=user_id, shortcode=code, kind=MediaKind.PHOTO)
    await mf.insert()
    return mf


@pytest.mark.asyncio
class TestFlush:
    async def test_empty_bucket_returns_none(self, test_user):
        result = await media_bucket.flush(test_user.id, "x", datetime(2026, 6, 2, 9, 0))
        assert result is None

    @patch("app.bot.media_bucket.classify_date", new_callable=AsyncMock)
    async def test_flush_with_descriptive(self, mock_classify, test_user):
        mock_classify.return_value = date(2026, 6, 1)
        await _loose(test_user.id, "att_1")
        await _loose(test_user.id, "att_2")

        msg = await media_bucket.flush(test_user.id, "вчора в парку", datetime(2026, 6, 2, 9, 0))

        assert msg is not None
        assert msg.source_type == SourceType.MEDIA
        assert msg.descriptive == "вчора в парку"
        assert msg.classified_date == date(2026, 6, 1)
        assert len(msg.media_file_ids) == 2
        # files now attached, bucket empty
        assert await media_bucket.has_loose_media(test_user.id) is False

    async def test_flush_empty_descriptive_uses_send_date(self, test_user):
        await _loose(test_user.id, "att_3")
        msg = await media_bucket.flush(test_user.id, "", datetime(2026, 6, 2, 9, 0))
        assert msg.descriptive is None
        assert msg.classified_date == date(2026, 6, 2)
