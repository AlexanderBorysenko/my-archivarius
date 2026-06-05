from datetime import datetime

from aiogram import Dispatcher, types, F
from aiogram.filters import CommandStart, Command

from app.models.user import User
from app.models.raw_message import RawMessage, MessageStatus
from app.models.inbound_event import InboundKind, Initiator
from app.services.bake import bake_messages
from app.services.intake import register_inbound_event, inflight_inbound_count
from app.core.events import event_bus
from app.bot import media_bucket
from app.models.media_file import MediaKind


def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_bake, Command("bake"))
    dp.message.register(cmd_web, Command("web"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(handle_skip, Command("skip"))
    dp.message.register(handle_voice, F.voice)
    dp.message.register(handle_photo, F.photo)
    dp.message.register(handle_video, F.video)
    dp.message.register(handle_video_note, F.video_note)
    dp.message.register(handle_unsupported, F.document | F.audio | F.sticker | F.animation)
    dp.message.register(handle_text, F.text)


async def cmd_start(message: types.Message):
    """Register user and send welcome message."""
    user = await User.find_one({"telegram_id": message.from_user.id})
    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )
        await user.insert()

    await message.answer(
        f"Привіт, {user.display_name}! 👋\n\n"
        "Я — твій AI-щоденник. Просто пиши або надсилай голосові "
        "повідомлення протягом дня, а коли будеш готовий — "
        "набери /bake щоб перетворити їх на запис у щоденнику.\n\n"
        "Команди:\n"
        "/bake — запікти повідомлення в запис\n"
        "/web — відкрити веб-інтерфейс\n"
        "/help — довідка"
    )


async def cmd_bake(message: types.Message):
    """Trigger the bake process."""
    user = await _get_user(message)
    if not user:
        return

    await media_bucket.flush(user.id, "", message.date or datetime.utcnow())

    # Don't bake while messages are still being ingested/processed by the worker.
    processing_count = await inflight_inbound_count(user.id)
    if processing_count > 0:
        await message.answer(
            f"⏳ Є {processing_count} повідомлень в процесі обробки. "
            "Зачекай завершення і спробуй знову."
        )
        return

    pending_count = await RawMessage.find(
        {"user_id": user.id, "status": MessageStatus.PENDING}
    ).count()

    if pending_count == 0:
        await message.answer("Буфер порожній — нічого запікати 🤷")
        return

    await message.answer(f"🔥 Запікаю {pending_count} повідомлень...")

    # Get all pending messages
    pending = await RawMessage.find(
        {"user_id": user.id, "status": MessageStatus.PENDING}
    ).to_list()

    user_id_str = str(user.id)
    try:
        entries = await bake_messages(user.id, pending)
        await event_bus.publish(user_id_str, "bake:complete", {
            "entries_created": len(entries),
            "entries": [
                {"id": str(e.id), "date": e.date.isoformat(), "preview": e.content[:200]}
                for e in entries
            ],
        })
        dates_str = ", ".join(e.date.strftime("%d.%m") for e in entries)
        await message.answer(
            f"✅ Готово! Створено {len(entries)} запис(ів) за дати: {dates_str}"
        )
    except Exception as exc:
        await event_bus.publish(user_id_str, "bake:error", {"detail": str(exc)[:300]})
        await message.answer(f"❌ Помилка запікання: {str(exc)[:200]}")


async def cmd_web(message: types.Message):
    """Send link to web interface."""
    # TODO: generate auth link
    await message.answer("🌐 Веб-інтерфейс: (посилання буде додано після деплою)")


async def cmd_help(message: types.Message):
    """Show help message."""
    await message.answer(
        "📖 Як користуватись:\n\n"
        "Надсилай мені текстові або голосові повідомлення "
        "протягом дня — я збережу їх у буфер.\n\n"
        "Коли будеш готовий, набери /bake — і я перетворю "
        "все на літературний запис у щоденнику.\n\n"
        "Команди:\n"
        "/bake — запікти повідомлення\n"
        "/web — відкрити веб-інтерфейс\n"
        "/help — ця довідка"
    )


async def handle_voice(message: types.Message, inbound_update_id: int):
    """Handle incoming voice — dedup, enqueue a durable job. The worker downloads + transcribes."""
    user = await _get_user(message)
    if not user:
        return

    voice = message.voice
    event = await register_inbound_event(
        channel="telegram",
        external_id=inbound_update_id,
        user_id=user.id,
        kind=InboundKind.VOICE,
        initiator=Initiator(
            channel="telegram",
            chat_id=message.chat.id,
            message_id=message.message_id,
        ),
        payload={"voice": {"file_id": voice.file_id, "duration": voice.duration}},
    )
    if event is None:
        return  # Telegram redelivery.

    await message.answer(f"🎙️ Отримано голосове ({voice.duration}с). Транскрибую...")
    await event_bus.publish(str(user.id), "buffer:update")

    # The worker (single CAS-claimer) owns download + transcription — no second writer races us.
    from app.services.worker import enqueue_hot
    enqueue_hot(event.event_id)


async def _gate_media(message: types.Message, inbound_update_id: int, user) -> bool:
    """Dedup a media update. Returns True if this is a fresh delivery to process."""
    event = await register_inbound_event(
        channel="telegram",
        external_id=inbound_update_id,
        user_id=user.id,
        kind=InboundKind.MEDIA,
        initiator=Initiator(
            channel="telegram",
            chat_id=message.chat.id,
            message_id=message.message_id,
        ),
        payload={"media": {"message_id": message.message_id}},
    )
    return event is not None


async def handle_photo(message: types.Message, inbound_update_id: int):
    user = await _get_user(message)
    if not user:
        return
    if not await _gate_media(message, inbound_update_id, user):
        return
    await media_bucket.ingest_media(user, message, MediaKind.PHOTO)


async def handle_video(message: types.Message, inbound_update_id: int):
    user = await _get_user(message)
    if not user:
        return
    if not await _gate_media(message, inbound_update_id, user):
        return
    await media_bucket.ingest_media(user, message, MediaKind.VIDEO)


async def handle_video_note(message: types.Message, inbound_update_id: int):
    user = await _get_user(message)
    if not user:
        return
    if not await _gate_media(message, inbound_update_id, user):
        return
    await media_bucket.ingest_media(user, message, MediaKind.VIDEO_NOTE)


async def handle_unsupported(message: types.Message):
    user = await _get_user(message)
    if not user:
        return
    await message.answer("Цей тип файлу поки не підтримується.")


async def handle_skip(message: types.Message):
    user = await _get_user(message)
    if not user:
        return
    await _flush_and_ack(user, message, "")


async def _flush_and_ack(user, message: types.Message, descriptive: str):
    msg = await media_bucket.flush(user.id, descriptive, message.date or datetime.utcnow())
    if not msg:
        await message.answer("Немає вкладень для опису.")
        return
    n = len(msg.media_file_ids)
    if descriptive.strip():
        await message.answer(f"📎 Опис додано до {n} вкладень.")
    else:
        await message.answer(f"📎 Збережено {n} вкладень без опису.")


async def handle_text(message: types.Message, inbound_update_id: int):
    """Handle incoming text — descriptive for pending media, or a normal note."""
    user = await _get_user(message)
    if not user:
        return

    # Descriptive / flush paths are pending-media UI actions, not new buffer notes —
    # they are naturally idempotent enough and predate the queue; gate only the note path.
    if message.text.strip() == "-":
        await _flush_and_ack(user, message, "")
        return

    if await media_bucket.has_loose_media(user.id):
        await _flush_and_ack(user, message, message.text)
        return

    event = await register_inbound_event(
        channel="telegram",
        external_id=inbound_update_id,
        user_id=user.id,
        kind=InboundKind.TEXT,
        initiator=Initiator(
            channel="telegram",
            chat_id=message.chat.id,
            message_id=message.message_id,
        ),
        payload={"text": {"content": message.text}},
    )
    if event is None:
        return  # Telegram redelivery.

    await event_bus.publish(str(user.id), "buffer:update")
    await message.answer("✅ Записано!")

    # The worker classifies + persists the note (sub-second); same UX as voice.
    from app.services.worker import enqueue_hot
    enqueue_hot(event.event_id)


async def _get_user(message: types.Message) -> User | None:
    """Get or prompt user to register."""
    user = await User.find_one({"telegram_id": message.from_user.id})
    if not user:
        await message.answer("Спершу набери /start для реєстрації.")
        return None
    return user
