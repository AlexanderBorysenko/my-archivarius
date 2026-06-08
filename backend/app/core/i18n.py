"""Localization for the Telegram bot, the completion notifier, and the settings API."""

SUPPORTED_LANGS = ("en", "uk", "ru")
DEFAULT_LANG = "en"

# Human-readable names used inside AI prompts as a content fallback language.
LANG_NAMES = {"en": "English", "uk": "Ukrainian", "ru": "Russian"}


def map_telegram_lang(code: str | None) -> str:
    """Map a Telegram language_code (e.g. 'en-US') to one of SUPPORTED_LANGS; default English."""
    if not code:
        return DEFAULT_LANG
    base = code.split("-")[0].lower()
    return base if base in SUPPORTED_LANGS else DEFAULT_LANG


def t(key: str, lang: str, **kwargs) -> str:
    """Translate `key` into `lang`, interpolating kwargs, with safe fallbacks."""
    catalog = TRANSLATIONS.get(lang) or TRANSLATIONS[DEFAULT_LANG]
    template = catalog.get(key) or TRANSLATIONS[DEFAULT_LANG].get(key, key)
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


# Localized display text for the default diary style (shown in Settings as a placeholder).
# Generation uses the neutral-English DEFAULT_STYLE in bake.py; this is the human-facing copy.
DEFAULT_STYLE_DISPLAY = {
    "en": "Style: a personal diary — first person, natural, not overly formal.",
    "uk": "Стиль: особистий щоденник — від першої особи, природній, не надто формальний.",
    "ru": "Стиль: личный дневник — от первого лица, естественный, не слишком формальный.",
}


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "Hi, {name}! 👋\n\n"
            "I'm your AI diary. Just write or send voice messages throughout the day, "
            "and when you're ready, type /bake to turn them into a diary entry.\n\n"
            "Commands:\n/bake — bake messages into an entry\n/web — open the web interface\n/help — help"
        ),
        "help": (
            "📖 How to use:\n\n"
            "Send me text or voice messages throughout the day — I'll save them to a buffer.\n\n"
            "When you're ready, type /bake — and I'll turn everything into a literary diary entry.\n\n"
            "Commands:\n/bake — bake messages\n/web — open the web interface\n/help — this help"
        ),
        "web_link": "🌐 Web interface: (link will be added after deployment)",
        "register_first": "Type /start first to register.",
        "bake_processing": "⏳ {count} messages are still being processed. Please wait and try again.",
        "buffer_empty": "Your buffer is empty — nothing to bake 🤷",
        "bake_start": "🔥 Baking {count} messages...",
        "bake_done": "✅ Done! Created {count} entr(ies) for dates: {dates}",
        "bake_error": "❌ Baking error: {error}",
        "voice_received": "🎙️ Got a voice message ({duration}s). Transcribing...",
        "ok_voice": "✅ Voice transcribed and saved!",
        "ok_text": "✅ Saved!",
        "ok_media": "✅ Saved!",
        "ok_generic": "✅ Done!",
        "err_processing": "❌ Processing error: {error}",
        "unsupported": "This file type is not supported yet.",
        "media_none": "No attachments to describe.",
        "media_described": "📎 Description added to {n} attachment(s).",
        "media_saved": "📎 Saved {n} attachment(s) without a description.",
        "text_saved": "✅ Saved!",
        "preview_failed": "Failed to generate the preview",
        "msg_not_found": "Message not found",
        "buffer_locked_baking": "Can't modify the buffer while baking is in progress",
        "cannot_edit_baked": "Can't edit a message that has already been baked",
        "msg_no_media": "The message contains no media",
        "duplicate_media": "Duplicate media files",
        "media_not_found_list": "Media file not found: {missing}",
        "api_processing_wait": "{count} messages are still being processed. Please wait until they finish.",
        "baking_in_progress": "Baking is already running",
        "api_buffer_empty": "The buffer is empty — nothing to bake",
        "entry_not_found_for_date": "No entry found for this date",
        "entry_not_found": "Entry not found",
        "no_originals_rebake": "No source messages to rebake from",
        "category_exists": "A category with this name already exists",
        "category_not_found": "Category not found",
        "cannot_delete_system_category": "System categories can't be deleted",
        "highlight_not_found": "Highlight not found",
        "media_not_found": "Media file not found",
        "file_unavailable": "The file is unavailable",
        "poster_not_found": "Poster not found",
        "unsupported_file_type": "Unsupported file type: {ct}",
        "file_too_large": "The file is too large",
        "media_ask_description": "📎 Got it. Send a text description or /skip.",
    },
    "uk": {
        "welcome": (
            "Привіт, {name}! 👋\n\n"
            "Я — твій AI-щоденник. Просто пиши або надсилай голосові повідомлення протягом дня, "
            "а коли будеш готовий — набери /bake щоб перетворити їх на запис у щоденнику.\n\n"
            "Команди:\n/bake — запікти повідомлення в запис\n/web — відкрити веб-інтерфейс\n/help — довідка"
        ),
        "help": (
            "📖 Як користуватись:\n\n"
            "Надсилай мені текстові або голосові повідомлення протягом дня — я збережу їх у буфер.\n\n"
            "Коли будеш готовий, набери /bake — і я перетворю все на літературний запис у щоденнику.\n\n"
            "Команди:\n/bake — запікти повідомлення\n/web — відкрити веб-інтерфейс\n/help — ця довідка"
        ),
        "web_link": "🌐 Веб-інтерфейс: (посилання буде додано після деплою)",
        "register_first": "Спершу набери /start для реєстрації.",
        "bake_processing": "⏳ Є {count} повідомлень в процесі обробки. Зачекай завершення і спробуй знову.",
        "buffer_empty": "Буфер порожній — нічого запікати 🤷",
        "bake_start": "🔥 Запікаю {count} повідомлень...",
        "bake_done": "✅ Готово! Створено {count} запис(ів) за дати: {dates}",
        "bake_error": "❌ Помилка запікання: {error}",
        "voice_received": "🎙️ Отримано голосове ({duration}с). Транскрибую...",
        "ok_voice": "✅ Голосове транскрибовано та записано!",
        "ok_text": "✅ Записано!",
        "ok_media": "✅ Збережено!",
        "ok_generic": "✅ Готово!",
        "err_processing": "❌ Помилка обробки: {error}",
        "unsupported": "Цей тип файлу поки не підтримується.",
        "media_none": "Немає вкладень для опису.",
        "media_described": "📎 Опис додано до {n} вкладень.",
        "media_saved": "📎 Збережено {n} вкладень без опису.",
        "text_saved": "✅ Записано!",
        "preview_failed": "Не вдалося згенерувати попередній перегляд",
        "msg_not_found": "Повідомлення не знайдено",
        "buffer_locked_baking": "Не можна змінювати буфер під час запікання",
        "cannot_edit_baked": "Не можна редагувати вже запечене повідомлення",
        "msg_no_media": "Повідомлення не містить медіа",
        "duplicate_media": "Дубльовані медіафайли",
        "media_not_found_list": "Медіафайл не знайдено: {missing}",
        "api_processing_wait": "Є {count} повідомлень в процесі обробки. Зачекайте завершення.",
        "baking_in_progress": "Запікання вже виконується",
        "api_buffer_empty": "Буфер порожній — нічого запікати",
        "entry_not_found_for_date": "Запис за цю дату не знайдено",
        "entry_not_found": "Запис не знайдено",
        "no_originals_rebake": "Немає оригіналів для перезапікання",
        "category_exists": "Категорія з такою назвою вже існує",
        "category_not_found": "Категорію не знайдено",
        "cannot_delete_system_category": "Системні категорії не можна видаляти",
        "highlight_not_found": "Хайлайт не знайдено",
        "media_not_found": "Медіафайл не знайдено",
        "file_unavailable": "Файл недоступний",
        "poster_not_found": "Постер не знайдено",
        "unsupported_file_type": "Непідтримуваний тип файлу: {ct}",
        "file_too_large": "Файл завеликий",
        "media_ask_description": "📎 Отримав. Надішли текстовий опис або /skip.",
    },
    "ru": {
        "welcome": (
            "Привет, {name}! 👋\n\n"
            "Я — твой AI-дневник. Просто пиши или отправляй голосовые сообщения в течение дня, "
            "а когда будешь готов — набери /bake, чтобы превратить их в запись дневника.\n\n"
            "Команды:\n/bake — запечь сообщения в запись\n/web — открыть веб-интерфейс\n/help — справка"
        ),
        "help": (
            "📖 Как пользоваться:\n\n"
            "Отправляй мне текстовые или голосовые сообщения в течение дня — я сохраню их в буфер.\n\n"
            "Когда будешь готов, набери /bake — и я превращу всё в литературную запись дневника.\n\n"
            "Команды:\n/bake — запечь сообщения\n/web — открыть веб-интерфейс\n/help — эта справка"
        ),
        "web_link": "🌐 Веб-интерфейс: (ссылка будет добавлена после деплоя)",
        "register_first": "Сначала набери /start для регистрации.",
        "bake_processing": "⏳ {count} сообщений ещё обрабатываются. Подожди завершения и попробуй снова.",
        "buffer_empty": "Буфер пуст — нечего запекать 🤷",
        "bake_start": "🔥 Запекаю {count} сообщений...",
        "bake_done": "✅ Готово! Создано {count} запис(ей) за даты: {dates}",
        "bake_error": "❌ Ошибка запекания: {error}",
        "voice_received": "🎙️ Получено голосовое ({duration}с). Транскрибирую...",
        "ok_voice": "✅ Голосовое транскрибировано и записано!",
        "ok_text": "✅ Записано!",
        "ok_media": "✅ Сохранено!",
        "ok_generic": "✅ Готово!",
        "err_processing": "❌ Ошибка обработки: {error}",
        "unsupported": "Этот тип файла пока не поддерживается.",
        "media_none": "Нет вложений для описания.",
        "media_described": "📎 Описание добавлено к {n} вложениям.",
        "media_saved": "📎 Сохранено {n} вложений без описания.",
        "text_saved": "✅ Записано!",
        "preview_failed": "Не удалось сгенерировать предпросмотр",
        "msg_not_found": "Сообщение не найдено",
        "buffer_locked_baking": "Нельзя изменять буфер во время запекания",
        "cannot_edit_baked": "Нельзя редактировать уже запечённое сообщение",
        "msg_no_media": "Сообщение не содержит медиа",
        "duplicate_media": "Дублирующиеся медиафайлы",
        "media_not_found_list": "Медиафайл не найден: {missing}",
        "api_processing_wait": "{count} сообщений ещё обрабатываются. Подождите завершения.",
        "baking_in_progress": "Запекание уже выполняется",
        "api_buffer_empty": "Буфер пуст — нечего запекать",
        "entry_not_found_for_date": "Запись за эту дату не найдена",
        "entry_not_found": "Запись не найдена",
        "no_originals_rebake": "Нет оригиналов для перезапекания",
        "category_exists": "Категория с таким названием уже существует",
        "category_not_found": "Категория не найдена",
        "cannot_delete_system_category": "Системные категории нельзя удалять",
        "highlight_not_found": "Хайлайт не найден",
        "media_not_found": "Медиафайл не найден",
        "file_unavailable": "Файл недоступен",
        "poster_not_found": "Постер не найден",
        "unsupported_file_type": "Неподдерживаемый тип файла: {ct}",
        "file_too_large": "Файл слишком большой",
        "media_ask_description": "📎 Получил. Отправь текстовое описание или /skip.",
    },
}
