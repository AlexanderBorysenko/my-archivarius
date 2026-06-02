"""Tests for macro processing inside the bake pipeline."""

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from app.models.media_file import MediaFile, MediaKind, MediaStatus
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.services.bake import bake_messages, _ensure_all_shortcodes


class TestEnsureWithExtraPlaced:
    def test_extra_placed_suppresses_inline_append(self):
        out = _ensure_all_shortcodes("text only", ["att_a", "att_b"], extra_placed={"att_a"})
        assert "attach:att_b" in out          # att_b appended
        assert "## Вкладення" in out
        assert out.count("attach:att_a") == 0  # att_a counted as placed, not appended


@pytest.mark.asyncio
class TestBakeMacros:
    @patch("app.services.bake.extract_highlights_for_entries", new_callable=AsyncMock)
    @patch("app.services.bake._call_claude", new_callable=AsyncMock)
    async def test_ai_gallery_normalized_and_not_double_appended(self, mock_claude, mock_hl, test_user):
        mock_hl.return_value = []
        # two photos in one media message; model emits a gallery macro with raw JSON
        a = MediaFile(user_id=test_user.id, shortcode="att_a", kind=MediaKind.PHOTO,
                      status=MediaStatus.READY, attached=True)
        b = MediaFile(user_id=test_user.id, shortcode="att_b", kind=MediaKind.PHOTO,
                      status=MediaStatus.READY, attached=True)
        await a.insert(); await b.insert()
        mock_claude.return_value = (
            'День був чудовий.\n\n'
            '<!-- macro:gallery {"images":["att_a","att_b"],"caption":"Прогулянка"} -->'
        )
        msg = RawMessage(user_id=test_user.id, source_type=SourceType.MEDIA,
                         media_file_ids=[a.id, b.id], descriptive="секрет",
                         telegram_message_id=0, classified_date=date(2026, 6, 2),
                         status=MessageStatus.PENDING)
        await msg.insert()

        entries = await bake_messages(test_user.id, [msg])
        content = entries[0].content

        assert "секрет" not in content                  # descriptive never leaked
        assert "## Вкладення" not in content            # not double-appended inline
        assert content.count("attach:att_a") == 0       # shortcodes live in the (base64) macro
        import re
        from app.services.macros.process import _decode_payload
        m = re.search(r"<!-- macro:gallery (\S+) -->", content)  # normalized to base64
        assert m
        payload = _decode_payload(m.group(1))
        assert payload["images"] == ["att_a", "att_b"]
        assert payload["caption"] == "Прогулянка"  # Cyrillic survives the base64 round-trip
