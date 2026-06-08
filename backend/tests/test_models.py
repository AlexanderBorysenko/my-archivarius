"""Tests for MongoDB models — CRUD operations and constraints."""

import pytest
from datetime import date, datetime

from app.models.user import User, CustomCategory
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.models.entry import Entry
from app.models.highlight import Highlight


@pytest.mark.asyncio
class TestUserModel:
    async def test_create_user(self):
        user = User(telegram_id=111, username="alice", display_name="Alice")
        await user.insert()

        found = await User.find_one({"telegram_id": 111})
        assert found is not None
        assert found.username == "alice"

    async def test_custom_categories(self):
        user = User(
            telegram_id=222,
            username="bob",
            display_name="Bob",
            custom_categories=[
                CustomCategory(name="health", description="Здоров'я"),
            ],
        )
        await user.insert()

        found = await User.get(user.id)
        assert len(found.custom_categories) == 1
        assert found.custom_categories[0].name == "health"


@pytest.mark.asyncio
class TestRawMessageModel:
    async def test_create_text_message(self, test_user):
        msg = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.TEXT,
            content="Hello!",
            telegram_message_id=42,
            classified_date=date(2026, 4, 22),
            status=MessageStatus.PENDING,
        )
        await msg.insert()

        found = await RawMessage.get(msg.id)
        assert found.content == "Hello!"
        assert found.status == MessageStatus.PENDING
        assert found.source_type == SourceType.TEXT

    async def test_filter_by_status(self, test_user):
        for i in range(3):
            msg = RawMessage(
                user_id=test_user.id,
                source_type=SourceType.TEXT,
                content=f"Msg {i}",
                telegram_message_id=i,
                classified_date=date(2026, 4, 22),
                status=MessageStatus.PENDING if i < 2 else MessageStatus.BAKED,
            )
            await msg.insert()

        pending = await RawMessage.find(
            {"user_id": test_user.id, "status": MessageStatus.PENDING}
        ).to_list()
        assert len(pending) == 2


@pytest.mark.asyncio
class TestEntryModel:
    async def test_create_entry(self, test_user):
        entry = Entry(
            user_id=test_user.id,
            date=date(2026, 4, 22),
            blocks=[{"type": "markdown", "text": "Запис щоденника."}],
            source_messages=[],
            version=1,
        )
        await entry.insert()

        found = await Entry.find_one({"user_id": test_user.id, "date": date(2026, 4, 22)})
        assert found is not None
        assert found.blocks == [{"type": "markdown", "text": "Запис щоденника."}]

    async def test_one_entry_per_date(self, test_user):
        """Verify we can find unique entry per user+date."""
        entry = Entry(
            user_id=test_user.id,
            date=date(2026, 4, 22),
            blocks=[{"type": "markdown", "text": "First version"}],
            source_messages=[],
            version=1,
        )
        await entry.insert()

        found = await Entry.find_one({"user_id": test_user.id, "date": date(2026, 4, 22)})
        found.blocks = [{"type": "markdown", "text": "Updated version"}]
        found.version = 2
        await found.save()

        all_entries = await Entry.find({"user_id": test_user.id, "date": date(2026, 4, 22)}).to_list()
        assert len(all_entries) == 1
        assert all_entries[0].version == 2


@pytest.mark.asyncio
class TestHighlightModel:
    async def test_create_highlight(self, test_user):
        h = Highlight(
            user_id=test_user.id,
            title="Важлива ідея",
            category="idea",
            content="Зміст ідеї",
            source_entries=[],
        )
        await h.insert()

        found = await Highlight.get(h.id)
        assert found.title == "Важлива ідея"
        assert found.category == "idea"


@pytest.mark.asyncio
class TestRawMessageEventId:
    async def test_event_id_defaults_none_and_persists(self, test_user):
        rm = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.VOICE,
            content="hi",
            telegram_message_id=1,
            classified_date=date.today(),
            status=MessageStatus.PENDING,
        )
        await rm.insert()
        assert rm.event_id is None

        rm2 = RawMessage(
            user_id=test_user.id,
            source_type=SourceType.VOICE,
            content="hi",
            telegram_message_id=2,
            classified_date=date.today(),
            status=MessageStatus.PENDING,
            event_id="evt-xyz",
        )
        await rm2.insert()
        fetched = await RawMessage.find_one({"event_id": "evt-xyz"})
        assert fetched is not None
        assert fetched.id == rm2.id


@pytest.mark.asyncio
class TestUserLanguage:
    async def test_default_language_is_en(self, test_user):
        refreshed = await User.get(test_user.id)
        assert refreshed.language == "en"

    async def test_language_can_be_set(self, test_user):
        test_user.language = "uk"
        await test_user.save()
        refreshed = await User.get(test_user.id)
        assert refreshed.language == "uk"
