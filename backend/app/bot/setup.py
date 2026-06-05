from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

from app.core.config import settings
from app.bot.handlers import register_handlers
from app.bot.middlewares import UpdateIdMiddleware

bot = Bot(token=settings.telegram_bot_token) if settings.telegram_bot_token else None
dp = Dispatcher()

dp.update.outer_middleware(UpdateIdMiddleware())
register_handlers(dp)


async def process_update(raw_update: dict):
    """Process a raw Telegram update (called from webhook endpoint)."""
    if bot is None:
        return
    update = types.Update.model_validate(raw_update, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
