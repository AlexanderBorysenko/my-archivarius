"""Bake service — transforms raw messages into literary diary entries via Claude API."""

import json
import logging
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Awaitable, Callable, Optional

import anthropic

from app.core.config import settings
from app.models.raw_message import RawMessage, MessageStatus, SourceType
from app.models.media_file import MediaFile
from app.models.entry import Entry
from app.models.user import User
from app.services.highlights import extract_highlights_for_entries
from app.services.macros import process_macros

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str, str], Awaitable[None]]
"""Async callback: (completed_steps, total_steps, current_label, phase)."""

CORE_RULES = """Ти — редактор особистого щоденника. Твоє завдання — перетворити сирі повідомлення (нотатки, голосові транскрипції) у зв'язний текст щоденникового запису.

Обов'язкові правила:
1. ЗБЕРЕЖИ весь смисловий зміст — не вигадуй фактів, не додавай того, чого не було.
2. Виправляй граматичні помилки та помилки транскрибації, але зберігай авторський стиль та характерні вирази.
3. Хронологічний порядок: якщо можна визначити послідовність подій — зберігай її.
4. Якщо є повтори (одне й те саме сказано в тексті і в голосовому) — об'єднай, не дублюй.
5. Формат: Markdown. Використовуй абзаци, **жирний** для акцентів, списки де доречно.
6. Відповідай ТІЛЬКИ текстом запису, без вступів типу "Ось ваш запис:" чи пояснень."""

DEFAULT_STYLE = """Стиль та оформлення:
- Структуруй запис за допомогою заголовків Markdown: використовуй `## Назва теми` для кожної тематичної секції. Якщо в секції є підтеми — використовуй `### Підтема`. Кожна секція — окрема тема чи подія дня. Придумай короткий, змістовний заголовок для кожної секції (наприклад: "## Ранкова пробіжка", "## Робочі справи", "## Вечірні роздуми"). НЕ використовуй `---` для розділення тем — тільки заголовки.
- Стиль — особистий щоденник: від першої особи, природній, не надто формальний."""

MEDIA_RULES = """Медіа-вкладення:
- Тобі надано реєстр медіа-файлів із підказками (descriptive). Опис — ЛИШЕ підказка, де доречно розмістити файл; НЕ включай текст опису в запис.
- Встав КОЖЕН файл як зображення-плейсхолдер у відповідному за змістом місці: `![](attach:SHORTCODE)`.
- Якщо неможливо визначити доречне місце — додай файл у кінці запису.
- Не вигадуй файлів, яких немає в реєстрі, і не повторюй той самий SHORTCODE двічі.

Макроси оформлення (необов'язкові, ЛИШЕ для фото):
- ГАЛЕРЕЯ для 2+ пов'язаних фото — на окремому рядку:
  <!-- macro:gallery {"images":["att_x","att_y"],"caption":"короткий підпис"} -->
- ФОТО З ОБТІКАННЯМ (текст обтікає одне фото збоку) — на окремому рядку перед потрібним абзацом:
  <!-- macro:figure {"image":"att_x","width":33,"align":"left","caption":"підпис"} -->
  width ∈ {25,33,50}; align ∈ {left,right}.
- Підпис (caption) пиши сам, короткий. Кожен SHORTCODE у макросі НЕ дублюй як inline `![](attach:...)`.
- Відео та поодинокі прості фото залишай як inline `![](attach:SHORTCODE)`."""


def build_system_prompt(user_style: str | None, with_media: bool = False) -> str:
    style = user_style.strip() if user_style and user_style.strip() else None
    prompt = f"{CORE_RULES}\n\n{style if style else DEFAULT_STYLE}"
    if with_media:
        prompt = f"{prompt}\n\n{MEDIA_RULES}"
    return prompt


async def bake_messages(
    user_id,
    messages: list[RawMessage],
    on_progress: Optional[ProgressFn] = None,
) -> list[Entry]:
    """Group messages by date and bake each group into an Entry.

    If `on_progress` is provided, it is awaited before each date is baked
    (phase="baking") and once before highlight extraction (phase="highlights").
    """
    user = await User.get(user_id)
    style_prompt = user.bake_style_prompt if user else None
    media_ctx = {
        f.shortcode: f.kind.value
        for f in await MediaFile.find({"user_id": user_id}).to_list()
    }

    by_date: dict[date, list[RawMessage]] = defaultdict(list)
    for msg in messages:
        by_date[msg.classified_date].append(msg)

    sorted_dates = sorted(by_date.keys())
    total = len(sorted_dates)

    entries = []
    for i, entry_date in enumerate(sorted_dates):
        if on_progress:
            await on_progress(i, total, f"запис за {entry_date.strftime('%d.%m.%Y')}", "baking")

        date_messages = by_date[entry_date]
        date_messages.sort(key=lambda m: m.created_at or datetime.min)

        entry = await _bake_date(user_id, entry_date, date_messages, style_prompt, media_ctx)
        entries.append(entry)

        for msg in date_messages:
            msg.status = MessageStatus.BAKED
            await msg.save()

    if on_progress:
        await on_progress(total, total, "вилучення хайлайтів", "highlights")

    try:
        await extract_highlights_for_entries(entries, user)
    except Exception as exc:
        logger.warning("Highlights extraction failed (non-critical): %s", exc)

    return entries


async def _build_media_registry(media_messages: list[RawMessage]) -> list[tuple[str, str, str]]:
    """Return (shortcode, kind, descriptive) tuples in chronological order."""
    entries: list[tuple[str, str, str]] = []
    for m in sorted(media_messages, key=lambda x: x.created_at or datetime.min):
        files = await MediaFile.find({"_id": {"$in": m.media_file_ids}}).to_list()
        desc = m.descriptive or "без опису"
        for f in files:
            entries.append((f.shortcode, f.kind.value, desc))
    return entries


def _format_media_registry(entries: list[tuple[str, str, str]]) -> str:
    lines = ["Медіа-реєстр (descriptive — лише підказка, НЕ включай у текст):"]
    for shortcode, kind, desc in entries:
        lines.append(f'- attach:{shortcode} ({kind}) — контекст: "{desc}"')
    return "\n".join(lines)


def _ensure_all_shortcodes(content: str, shortcodes: list[str], extra_placed=frozenset()) -> str:
    present = set(re.findall(r"attach:([A-Za-z0-9_]+)", content)) | set(extra_placed)
    missing = [s for s in shortcodes if s not in present]
    if not missing:
        return content
    appendix = "\n\n## Вкладення\n\n" + "\n\n".join(f"![](attach:{s})" for s in missing)
    return content + appendix


async def _bake_date(
    user_id,
    entry_date: date,
    messages: list[RawMessage],
    style_prompt: str | None = None,
    media_ctx: dict | None = None,
) -> Entry:
    """Bake messages for a single date into an Entry."""
    media_ctx = media_ctx or {}
    narrative = [m for m in messages if m.source_type in (SourceType.TEXT, SourceType.VOICE)]
    media = [m for m in messages if m.source_type == SourceType.MEDIA]
    registry = await _build_media_registry(media)
    shortcodes = [e[0] for e in registry]
    registry_text = _format_media_registry(registry) if registry else ""

    existing = await Entry.find_one({"user_id": user_id, "date": entry_date})

    if existing:
        content = await _bake_append(
            existing.content, narrative, entry_date, style_prompt, registry_text, bool(registry)
        )
        content, macro_used = process_macros(content, media_ctx)
        content = _ensure_all_shortcodes(content, shortcodes, extra_placed=macro_used)
        existing.content = content
        existing.source_messages.extend([msg.id for msg in messages])
        existing.version = (existing.version or 1) + 1
        existing.highlights_checked = False
        existing.updated_at = datetime.utcnow()
        await existing.save()
        return existing
    else:
        content = await _bake_new(
            narrative, entry_date, style_prompt, registry_text, bool(registry)
        )
        content, macro_used = process_macros(content, media_ctx)
        content = _ensure_all_shortcodes(content, shortcodes, extra_placed=macro_used)
        entry = Entry(
            user_id=user_id,
            date=entry_date,
            content=content,
            source_messages=[msg.id for msg in messages],
            version=1,
        )
        await entry.insert()
        return entry


async def _bake_new(
    messages: list[RawMessage], entry_date: date, style_prompt: str | None = None,
    registry_text: str = "", with_media: bool = False,
) -> str:
    """Generate a new diary entry from messages."""
    formatted_date = entry_date.strftime("%d %B %Y")
    messages_text = _format_messages(messages) if messages else "(немає текстових повідомлень)"
    media_block = f"\n\n{registry_text}\n" if registry_text else ""
    user_prompt = (
        f"Дата: {formatted_date}\n\n"
        f"Сирі повідомлення (хронологічно):\n\n{messages_text}\n"
        f"{media_block}\n"
        f"Створи щоденниковий запис за цю дату."
    )
    return await _call_claude(user_prompt, style_prompt=style_prompt,
                              temperature=0.7, max_tokens=4096, with_media=with_media)


async def _bake_append(
    existing_content: str, new_messages: list[RawMessage], entry_date: date,
    style_prompt: str | None = None, registry_text: str = "", with_media: bool = False,
) -> str:
    """Append new messages to an existing diary entry."""
    formatted_date = entry_date.strftime("%d %B %Y")
    messages_text = _format_messages(new_messages) if new_messages else "(немає нових текстових повідомлень)"
    media_block = f"\n\n{registry_text}\n" if registry_text else ""
    user_prompt = (
        f"Дата: {formatted_date}\n\n"
        f"Існуючий запис:\n---\n{existing_content}\n---\n\n"
        f"Нові повідомлення, які потрібно інтегрувати:\n\n{messages_text}\n"
        f"{media_block}\n"
        f"Доповни існуючий запис новою інформацією. "
        f"Збережи вже наявний текст, наявні плейсхолдери `![](attach:...)` та макроси `<!-- macro:... -->`. "
        f"Не дублюй те, що вже описано. Поверни ПОВНИЙ оновлений текст запису."
    )
    return await _call_claude(user_prompt, style_prompt=style_prompt,
                              temperature=0.5, max_tokens=4096, with_media=with_media)


def _format_messages(messages: list[RawMessage]) -> str:
    """Format messages into the prompt template."""
    lines = []
    for msg in messages:
        time_str = msg.created_at.strftime("%H:%M") if msg.created_at else "??:??"
        source = msg.source_type.value  # "text" or "voice"
        lines.append(f"[{time_str}] ({source}): {msg.content}")
    return "\n".join(lines)


async def _call_claude(
    user_prompt: str,
    style_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_retries: int = 3,
    with_media: bool = False,
) -> str:
    """Call Claude API with retry logic."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    system_prompt = build_system_prompt(style_prompt, with_media=with_media)

    last_error = None
    for attempt in range(max_retries):
        try:
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text.strip()

        except anthropic.RateLimitError:
            import asyncio

            wait = 2 ** (attempt + 1)
            logger.warning("Rate limit hit, retrying in %ds", wait)
            await asyncio.sleep(wait)
            last_error = "rate_limit"

        except anthropic.APIError as exc:
            logger.error("Claude API error on attempt %d: %s", attempt + 1, exc)
            last_error = exc
            break

    logger.error("Bake failed after retries (%s), returning raw text", last_error)
    return f"[Автоматичне запікання не вдалося. Сирі повідомлення:]\n\n{user_prompt}"
