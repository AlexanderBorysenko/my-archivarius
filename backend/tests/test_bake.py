"""Tests for bake service — message grouping and entry creation."""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.models.entry import Entry
from app.models.user import User
from app.services.bake import bake_messages, _format_messages, build_system_prompt, CORE_RULES, DEFAULT_STYLE


@pytest.mark.asyncio
class TestFormatMessages:
    async def test_format_text_and_voice(self, test_user):
        msgs = [
            RawMessage(
                user_id=test_user.id,
                source_type=SourceType.TEXT,
                content="Привіт!",
                telegram_message_id=1,
                classified_date=date(2026, 4, 22),
                status=MessageStatus.PENDING,
                created_at=datetime(2026, 4, 22, 8, 15),
            ),
            RawMessage(
                user_id=test_user.id,
                source_type=SourceType.VOICE,
                content="Зустрівся з другом",
                telegram_message_id=2,
                classified_date=date(2026, 4, 22),
                status=MessageStatus.PENDING,
                created_at=datetime(2026, 4, 22, 10, 30),
            ),
        ]
        result = _format_messages(msgs)
        assert "[08:15] (text): Привіт!" in result
        assert "[10:30] (voice): Зустрівся з другом" in result


@pytest.mark.asyncio
class TestBakeMessages:
    @patch("app.services.bake.extract_highlights_for_entries", new_callable=AsyncMock)
    @patch("app.services.bake._call_claude", new_callable=AsyncMock)
    async def test_single_date_creates_entry(self, mock_claude, mock_highlights, test_user):
        mock_claude.return_value = "Чудовий день. Прокинувся рано і пішов гуляти."
        mock_highlights.return_value = []

        msg = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.TEXT,
            content="Гарний день, гуляв у парку",
            telegram_message_id=1,
            classified_date=date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()

        entries = await bake_messages(test_user.id, [msg])

        assert len(entries) == 1
        assert entries[0].date == date(2026, 4, 22)
        assert entries[0].content == "Чудовий день. Прокинувся рано і пішов гуляти."
        assert len(entries[0].source_messages) == 1

        # Check message is now baked
        updated_msg = await RawMessage.get(msg.id)
        assert updated_msg.status == MessageStatus.BAKED

    @patch("app.services.bake.extract_highlights_for_entries", new_callable=AsyncMock)
    @patch("app.services.bake._call_claude", new_callable=AsyncMock)
    async def test_multiple_dates_creates_multiple_entries(self, mock_claude, mock_highlights, test_user):
        mock_claude.return_value = "Запис за день."
        mock_highlights.return_value = []

        msg1 = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.TEXT,
            content="Msg for day 1",
            telegram_message_id=1,
            classified_date=date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        msg2 = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.TEXT,
            content="Msg for day 2",
            telegram_message_id=2,
            classified_date=date(2026, 4, 23),
            status=MessageStatus.PENDING,
        )
        await msg1.insert()
        await msg2.insert()

        entries = await bake_messages(test_user.id, [msg1, msg2])

        assert len(entries) == 2
        dates = {e.date for e in entries}
        assert date(2026, 4, 22) in dates
        assert date(2026, 4, 23) in dates

    @patch("app.services.bake.extract_highlights_for_entries", new_callable=AsyncMock)
    @patch("app.services.bake._call_claude", new_callable=AsyncMock)
    async def test_append_to_existing_entry(self, mock_claude, mock_highlights, test_user):
        mock_claude.return_value = "Оновлений запис з новою інформацією."
        mock_highlights.return_value = []

        # Create existing entry
        existing = Entry(
            user_id=test_user.id,
            date=date(2026, 4, 22),
            content="Ранковий запис.",
            source_messages=[],
            version=1,
        )
        await existing.insert()

        msg = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.TEXT,
            content="Ввечері було класно",
            telegram_message_id=3,
            classified_date=date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()

        entries = await bake_messages(test_user.id, [msg])

        assert len(entries) == 1
        assert entries[0].version == 2
        assert entries[0].content == "Оновлений запис з новою інформацією."

        # Verify only 1 entry for this date (not a duplicate)
        all_entries = await Entry.find({"date": date(2026, 4, 22)}).to_list()
        assert len(all_entries) == 1

    @patch("app.services.bake.extract_highlights_for_entries", new_callable=AsyncMock)
    @patch("app.services.bake._call_claude", new_callable=AsyncMock)
    async def test_on_progress_reports_each_date_then_highlights(self, mock_claude, mock_highlights, test_user):
        mock_claude.return_value = "Запис."
        mock_highlights.return_value = []

        msg1 = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="day1",
            telegram_message_id=1, classified_date=date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        msg2 = RawMessage(
            user_id=test_user.id, source_type=SourceType.TEXT, content="day2",
            telegram_message_id=2, classified_date=date(2026, 4, 23),
            status=MessageStatus.PENDING,
        )
        await msg1.insert()
        await msg2.insert()

        calls = []

        async def record(completed, total, label, phase):
            calls.append((completed, total, phase))

        await bake_messages(test_user.id, [msg1, msg2], on_progress=record)

        # Two "baking" reports (one per date) + one final "highlights" report
        baking = [c for c in calls if c[2] == "baking"]
        assert len(baking) == 2
        assert all(total == 2 for _, total, _ in baking)
        assert calls[-1] == (2, 2, "highlights")


@pytest.mark.asyncio
class TestBuildSystemPrompt:
    async def test_none_returns_core_plus_default(self):
        result = build_system_prompt(None)
        assert CORE_RULES in result
        assert DEFAULT_STYLE in result

    async def test_custom_style_replaces_default(self):
        custom = "Пиши коротко, як SMS."
        result = build_system_prompt(custom)
        assert CORE_RULES in result
        assert custom in result
        assert DEFAULT_STYLE not in result

    async def test_empty_string_treated_as_none(self):
        result = build_system_prompt("")
        assert DEFAULT_STYLE in result

    async def test_whitespace_only_treated_as_none(self):
        result = build_system_prompt("   ")
        assert DEFAULT_STYLE in result
