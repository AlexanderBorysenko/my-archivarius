"""Tests for media handling in the bake pipeline."""

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from app.models.media_file import MediaFile, MediaKind, MediaStatus
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.services.bake import bake_messages, _ensure_all_shortcodes


class TestCompletenessPass:
    def test_appends_missing_shortcodes(self):
        content = "Текст із ![](attach:att_a) всередині."
        out = _ensure_all_shortcodes(content, ["att_a", "att_b"])
        assert "attach:att_a" in out
        assert "## Вкладення" in out
        assert "![](attach:att_b)" in out

    def test_noop_when_all_present(self):
        content = "![](attach:att_a) ![](attach:att_b)"
        out = _ensure_all_shortcodes(content, ["att_a", "att_b"])
        assert "## Вкладення" not in out


@pytest.mark.asyncio
class TestBakeWithMedia:
    @patch("app.services.bake.extract_highlights_for_entries", new_callable=AsyncMock)
    @patch("app.services.bake._call_claude", new_callable=AsyncMock)
    async def test_media_shortcodes_embedded_and_descriptive_not_leaked(
        self, mock_claude, mock_highlights, test_user
    ):
        # Model "forgets" the media; completeness pass must add it.
        mock_claude.return_value = "Гарний день у парку."
        mock_highlights.return_value = []

        mf = MediaFile(
            user_id=test_user.id, shortcode="att_park", kind=MediaKind.PHOTO,
            status=MediaStatus.READY, attached=True,
        )
        await mf.insert()

        media_msg = RawMessage(
            user_id=test_user.id, source_type=SourceType.MEDIA,
            media_file_ids=[mf.id], descriptive="секретна підказка розташування",
            telegram_message_id=0, classified_date=date(2026, 6, 2),
            status=MessageStatus.PENDING,
        )
        await media_msg.insert()

        entries = await bake_messages(test_user.id, [media_msg])

        assert len(entries) == 1
        content = entries[0].content
        assert "attach:att_park" in content                    # embedded
        assert "секретна підказка розташування" not in content  # descriptive never leaked
