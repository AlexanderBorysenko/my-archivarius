"""aiogram middlewares for the Telegram channel adapter."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update


class UpdateIdMiddleware(BaseMiddleware):
    """Expose the Telegram update_id to handlers as `inbound_update_id`.

    Registered on the update observer, so `event` is the whole Update and
    `event.update_id` is directly available. Handlers receive it via aiogram's
    data injection by declaring an `inbound_update_id: int` parameter.
    """

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        data["inbound_update_id"] = event.update_id
        return await handler(event, data)
