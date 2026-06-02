"""Tests for media manifests in entry/buffer serialization."""

import pytest
from datetime import date

from app.models.entry import Entry
from app.models.media_file import MediaFile, MediaKind, MediaStatus
from app.api.entries import _entry_full


@pytest.mark.asyncio
class TestEntryManifest:
    async def test_manifest_built_from_content(self, test_user):
        mf = MediaFile(
            user_id=test_user.id, shortcode="att_man", kind=MediaKind.VIDEO,
            status=MediaStatus.READY, mime="video/mp4", width=1920, height=1080,
            poster_key="/x/att_man_poster.jpg",
        )
        await mf.insert()

        entry = Entry(
            user_id=test_user.id, date=date(2026, 6, 2),
            content="Запис ![](attach:att_man) кінець.", source_messages=[], version=1,
        )
        await entry.insert()

        data = await _entry_full(entry, [], test_user.id)
        assert "att_man" in data["media"]
        assert data["media"]["att_man"]["kind"] == "video"
        assert data["media"]["att_man"]["has_poster"] is True

    async def test_empty_when_no_placeholders(self, test_user):
        entry = Entry(
            user_id=test_user.id, date=date(2026, 6, 3),
            content="Без медіа.", source_messages=[], version=1,
        )
        await entry.insert()
        data = await _entry_full(entry, [], test_user.id)
        assert data["media"] == {}


from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.api.buffer import _serialize_buffer_message


@pytest.mark.asyncio
class TestBufferManifest:
    async def test_media_message_enriched(self, test_user):
        mf = MediaFile(
            user_id=test_user.id, shortcode="att_buf", kind=MediaKind.PHOTO,
            status=MediaStatus.READY,
        )
        await mf.insert()
        msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.MEDIA,
            media_file_ids=[mf.id], descriptive="на морі",
            telegram_message_id=0, classified_date=date(2026, 6, 2),
            status=MessageStatus.PENDING,
        )
        await msg.insert()

        data = await _serialize_buffer_message(msg)
        assert data["descriptive"] == "на морі"
        assert len(data["media_files"]) == 1
        assert data["media_files"][0]["shortcode"] == "att_buf"

    async def test_text_message_unchanged(self, test_user):
        msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="привіт",
            telegram_message_id=1, classified_date=date(2026, 6, 2),
            status=MessageStatus.PENDING,
        )
        await msg.insert()
        data = await _serialize_buffer_message(msg)
        assert "media_files" not in data
        assert data["content"] == "привіт"
