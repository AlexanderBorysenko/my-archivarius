"""Completion notifier / channel router.

Decides WHO gets told a job finished, by inspecting initiator.channel, and delegates
the actual Telegram send to the bot (imported lazily so the worker stays channel-pure
and this module imports without aiogram present until a telegram send actually happens).
"""

import logging

from app.core.events import event_bus
from app.models.inbound_event import Initiator
from app.models.user import User
from app.core.i18n import t, DEFAULT_LANG

logger = logging.getLogger(__name__)

_OK_KEY = {"voice": "ok_voice", "text": "ok_text", "media": "ok_media"}


async def _telegram_send(chat_id: int, text: str) -> None:
    """Delegate to the Telegram adapter. Lazy import keeps the worker channel-pure."""
    from app.bot.setup import bot

    if bot is None:
        logger.warning("Telegram bot unavailable; dropping notification to chat %s", chat_id)
        return
    await bot.send_message(chat_id, text)


async def notify_outcome(
    *,
    user_id: str,
    initiator: Initiator,
    ok: bool,
    kind: str,
    error: str | None = None,
) -> None:
    """Route a job outcome to the initiating channel. Always publishes buffer:update (SSE)."""
    await event_bus.publish(user_id, "buffer:update")

    if initiator.channel == "telegram" and initiator.chat_id is not None:
        user = await User.get(user_id)
        lang = user.language if user else DEFAULT_LANG
        if ok:
            text = t(_OK_KEY.get(kind, "ok_generic"), lang)
        else:
            text = t("err_processing", lang, error=str(error)[:200])
        await _telegram_send(initiator.chat_id, text)
    # web (and any non-telegram channel) gets the SSE publish above and nothing else.
