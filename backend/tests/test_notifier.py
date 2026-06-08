"""Tests for the completion notifier / channel router."""

import pytest
from unittest.mock import AsyncMock, patch

from app.models.inbound_event import Initiator
from app.services import notifier
from app.core.events import event_bus


@pytest.mark.asyncio
@patch("app.services.notifier._telegram_send", new_callable=AsyncMock)
async def test_success_is_localized(mock_send, test_user):
    test_user.language = "en"
    await test_user.save()
    from app.services.notifier import notify_outcome
    init = Initiator(channel="telegram", chat_id=123, message_id=1)
    await notify_outcome(user_id=str(test_user.id), initiator=init, ok=True, kind="voice")
    mock_send.assert_awaited_once()
    args, _ = mock_send.call_args
    assert args[1] == "✅ Voice transcribed and saved!"


@pytest.mark.asyncio
@patch("app.services.notifier._telegram_send", new_callable=AsyncMock)
async def test_error_is_localized(mock_send, test_user):
    test_user.language = "uk"
    await test_user.save()
    from app.services.notifier import notify_outcome
    init = Initiator(channel="telegram", chat_id=123, message_id=1)
    await notify_outcome(user_id=str(test_user.id), initiator=init, ok=False, kind="voice", error="boom")
    args, _ = mock_send.call_args
    assert args[1].startswith("❌ Помилка обробки")


@pytest.mark.asyncio
async def test_web_initiator_publishes_sse_only(test_user):
    published = []

    async def fake_publish(uid, event, data=None):
        published.append((uid, event))

    sent = AsyncMock()
    with patch.object(event_bus, "publish", fake_publish), \
         patch.object(notifier, "_telegram_send", sent):
        await notifier.notify_outcome(
            user_id=str(test_user.id),
            initiator=Initiator(channel="web", chat_id=None, message_id=None),
            ok=True,
            kind="voice",
        )
    sent.assert_not_awaited()
    assert (str(test_user.id), "buffer:update") in published
