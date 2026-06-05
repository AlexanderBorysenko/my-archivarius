"""Handler-level tests using fake message objects."""

import pytest
from datetime import date, datetime
from types import SimpleNamespace
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

        # Bucket is full → hits _flush_and_ack before the dedup gate; no mock needed.
        await handlers.handle_text(_msg(text="на пляжі"), inbound_update_id=1001)

        media_msgs = await RawMessage.find({"source_type": SourceType.MEDIA}).to_list()
        assert len(media_msgs) == 1
        assert media_msgs[0].descriptive == "на пляжі"
        text_msgs = await RawMessage.find({"source_type": SourceType.TEXT}).to_list()
        assert text_msgs == []

    @patch("app.services.worker.enqueue_hot")
    @patch("app.bot.handlers.register_inbound_event", new_callable=AsyncMock)
    async def test_text_note_enqueues_worker_job(self, mock_register, mock_enqueue, test_user):
        # Fresh delivery — gate returns an event with an event_id.
        mock_register.return_value = SimpleNamespace(event_id="evt-text-xyz")

        await handlers.handle_text(_msg(text="звичайна нотатка"), inbound_update_id=1002)

        mock_register.assert_awaited_once()
        # The note is handed to the worker, not inserted inline by the handler.
        mock_enqueue.assert_called_once_with("evt-text-xyz")
        text_msgs = await RawMessage.find({"source_type": SourceType.TEXT}).to_list()
        assert text_msgs == []


@pytest.mark.asyncio
class TestSkip:
    async def test_skip_flushes_empty(self, test_user):
        await _loose(test_user.id)
        await handlers.handle_skip(_msg(text="/skip"))
        media_msgs = await RawMessage.find({"source_type": SourceType.MEDIA}).to_list()
        assert len(media_msgs) == 1
        assert media_msgs[0].descriptive is None
