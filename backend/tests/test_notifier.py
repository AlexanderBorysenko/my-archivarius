"""Tests for the completion notifier / channel router."""

import pytest
from unittest.mock import AsyncMock, patch

from app.models.inbound_event import Initiator
from app.services import notifier
from app.core.events import event_bus


@pytest.mark.asyncio
class TestNotifyOutcome:
    async def test_telegram_success_sends_message(self):
        sent = AsyncMock()
        with patch.object(notifier, "_telegram_send", sent):
            await notifier.notify_outcome(
                user_id="u1",
                initiator=Initiator(channel="telegram", chat_id=42, message_id=7),
                ok=True,
                kind="voice",
            )
        sent.assert_awaited_once()
        args, kwargs = sent.call_args
        assert args[0] == 42  # chat_id
        assert "✅" in args[1]

    async def test_telegram_failure_sends_error(self):
        sent = AsyncMock()
        with patch.object(notifier, "_telegram_send", sent):
            await notifier.notify_outcome(
                user_id="u1",
                initiator=Initiator(channel="telegram", chat_id=42, message_id=7),
                ok=False,
                kind="voice",
                error="boom",
            )
        sent.assert_awaited_once()
        assert "❌" in sent.call_args.args[1]

    async def test_web_initiator_publishes_sse_only(self):
        published = []

        async def fake_publish(uid, event, data=None):
            published.append((uid, event))

        sent = AsyncMock()
        with patch.object(event_bus, "publish", fake_publish), \
             patch.object(notifier, "_telegram_send", sent):
            await notifier.notify_outcome(
                user_id="u9",
                initiator=Initiator(channel="web", chat_id=None, message_id=None),
                ok=True,
                kind="voice",
            )
        sent.assert_not_awaited()
        assert ("u9", "buffer:update") in published
