"""Handler-level tests using fake message objects."""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.media_file import MediaFile, MediaKind
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.bot import handlers


def _msg(text=None, from_id=123456789):
    m = MagicMock()
    m.from_user.id = from_id
    m.text = text
    m.date = datetime(2026, 6, 2, 10, 0)
    m.message_id = 7
    m.answer = AsyncMock()
    return m


async def _loose(user_id):
    mf = MediaFile(user_id=user_id, shortcode="att_h1", kind=MediaKind.PHOTO)
    await mf.insert()
    return mf


@pytest.mark.asyncio
class TestTextAsDescriptive:
    @patch("app.bot.media_bucket.classify_date", new_callable=AsyncMock)
    async def test_text_becomes_descriptive_when_bucket_full(self, mock_classify, test_user):
        mock_classify.return_value = date(2026, 6, 2)
        await _loose(test_user.id)

        await handlers.handle_text(_msg(text="на пляжі"))

        media_msgs = await RawMessage.find({"source_type": SourceType.MEDIA}).to_list()
        assert len(media_msgs) == 1
        assert media_msgs[0].descriptive == "на пляжі"
        text_msgs = await RawMessage.find({"source_type": SourceType.TEXT}).to_list()
        assert text_msgs == []

    @patch("app.bot.handlers.classify_date", new_callable=AsyncMock)
    async def test_text_is_normal_note_when_bucket_empty(self, mock_classify, test_user):
        mock_classify.return_value = date(2026, 6, 2)

        await handlers.handle_text(_msg(text="звичайна нотатка"))

        text_msgs = await RawMessage.find({"source_type": SourceType.TEXT}).to_list()
        assert len(text_msgs) == 1
        assert text_msgs[0].content == "звичайна нотатка"


@pytest.mark.asyncio
class TestSkip:
    async def test_skip_flushes_empty(self, test_user):
        await _loose(test_user.id)
        await handlers.handle_skip(_msg(text="/skip"))
        media_msgs = await RawMessage.find({"source_type": SourceType.MEDIA}).to_list()
        assert len(media_msgs) == 1
        assert media_msgs[0].descriptive is None
