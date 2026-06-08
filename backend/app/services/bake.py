"""Bake service — transforms raw messages into literary diary entries via Claude API."""

import json
import logging
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
from app.services.blocks import build_blocks_schema, normalize_blocks, ensure_all_blocks
from app.services.llm import output_config

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str, str], Awaitable[None]]
"""Async callback: (completed_steps, total_steps, current_label, phase)."""

CORE_RULES = """Ти — редактор особистого щоденника. Твоє завдання — перетворити сирі повідомлення (нотатки, голосові транскрипції) у зв'язний текст щоденникового запису.

Обов'язкові правила:
1. ЗБЕРЕЖИ весь смисловий зміст — не вигадуй фактів, не додавай того, чого не було.
2. Виправляй граматичні помилки та помилки транскрибації, але зберігай авторський стиль та характерні вирази.
3. Хронологічний порядок: якщо можна визначити послідовність подій — зберігай її.
4. Якщо є повтори (одне й те саме сказано в тексті і в голосовому) — об'єднай, не дублюй.
5. Прозу пиши у блоках типу "markdown" (поле text) звичайним Markdown: абзаци, **жирний**, списки.
6. Не додавай вступів типу "Ось ваш запис:" чи пояснень — лише блоки запису."""

BLOCKS_RULES = """Структура запису — впорядкований список блоків (blocks):
- "markdown" — проза (поле text). Структуруй запис заголовками `## Назва секції` (за потреби `### Підтема`); кожна секція — окрема тема чи подія дня. Не використовуй `---` для розділення — лише заголовки.
- Розбивай прозу на кілька markdown-блоків так, щоб медіа-блоки стояли між абзацами у змістовно доречних місцях."""

DEFAULT_STYLE = """Стиль: особистий щоденник — від першої особи, природній, не надто формальний."""

MEDIA_RULES = """Медіа-блоки (коли надано медіа-реєстр):
- Розмісти КОЖЕН файл із реєстру у відповідному за змістом місці. descriptive — лише підказка, де доречно; НЕ виводь його в текст.
- 2+ пов'язаних ФОТО (одна подія/локація) → блок "gallery" (images: список shortcode; caption: короткий підпис).
- Одне медіа (фото АБО відео) → блок "figure" (media: shortcode; width ∈ {25,33,50,100}; align ∈ {left,right,center,full}; caption):
  • align left/right (width 25/33/50) — фото збоку, текст його обтікає (float).
  • width 50 + align center — змістовний кадр окремо по центру.
  • width 100 + align full — ключовий або широкий кадр / відео на всю ширину.
- ПОРЯДОК обтічних фото (align left/right) — критично: став такий "figure" ПЕРЕД тим markdown-блоком, чий текст його описує (обтікання діє лише на текст ПІСЛЯ фото в списку блоків; якщо поставити фото після тексту — обтікання не спрацює). Обтікання скидається на кожному заголовку (`##`/`###`), тож тримай обтічне фото в межах його секції: після заголовка секції, перед її прозою. Фото align center/full порядок не важливий — став між абзацами де доречно.
- Підпис (caption) пиши сам, короткий. Не використовуй один і той самий shortcode двічі. Галерея — лише для фото; відео завжди як окремий "figure"."""


def build_system_prompt(user_style: str | None, with_media: bool = False) -> str:
    style = user_style.strip() if user_style and user_style.strip() else None
    prompt = f"{CORE_RULES}\n\n{BLOCKS_RULES}\n\n{style if style else DEFAULT_STYLE}"
    if with_media:
        prompt = f"{prompt}\n\n{MEDIA_RULES}"
    return prompt


def _split_messages(messages: list[RawMessage]) -> tuple[list[RawMessage], list[RawMessage]]:
    """Split into (narrative, media) by source type."""
    narrative = [m for m in messages if m.source_type in (SourceType.TEXT, SourceType.VOICE)]
    media = [m for m in messages if m.source_type == SourceType.MEDIA]
    return narrative, media


async def _media_ctx(user_id) -> dict[str, str]:
    """User-wide shortcode -> kind map, used to normalize media blocks."""
    return {
        f.shortcode: f.kind.value
        for f in await MediaFile.find({"user_id": user_id}).to_list()
    }


async def _render_date_content(
    entry_date: date,
    messages: list[RawMessage],
    style_prompt: str | None,
    media_ctx: dict,
    *,
    existing_blocks: list | None,
) -> list[dict]:
    """Produce the finished block list for one date from its messages (no DB writes).

    ``existing_blocks is None`` → fresh generation (``_bake_new``);
    otherwise → integrate the messages into it (``_bake_append``).
    """
    narrative, media = _split_messages(messages)
    registry = await _build_media_registry(media)
    shortcodes = [e[0] for e in registry]
    registry_text = _format_media_registry(registry) if registry else ""

    if existing_blocks is None:
        raw = await _bake_new(narrative, entry_date, style_prompt, registry_text, bool(registry))
    else:
        raw = await _bake_append(
            existing_blocks, narrative, entry_date, style_prompt, registry_text, bool(registry)
        )

    blocks, used = normalize_blocks(raw, media_ctx)
    return ensure_all_blocks(blocks, shortcodes, used)


async def _save_entry(entry: Entry) -> Entry:
    """Persist a regenerated/updated entry: bump version, reset highlights, save."""
    entry.version = (entry.version or 1) + 1
    entry.highlights_checked = False
    entry.updated_at = datetime.utcnow()
    await entry.save()
    return entry


async def _safe_extract_highlights(entries: list[Entry], user) -> None:
    """Extract highlights, swallowing failures (non-critical to the bake)."""
    try:
        await extract_highlights_for_entries(entries, user)
    except Exception as exc:
        logger.warning("Highlights extraction failed (non-critical): %s", exc)


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
    media_ctx = await _media_ctx(user_id)

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

    await _safe_extract_highlights(entries, user)
    return entries


async def rebake_entry(
    user_id,
    entry: Entry,
    on_progress: Optional[ProgressFn] = None,
) -> list[Entry]:
    """Regenerate an existing entry from scratch using its own source messages.

    Fully replaces the entry's content (discarding manual edits), keeps
    `source_messages` unchanged, leaves message status untouched, and re-extracts
    highlights. Returns `[entry]` to match the bake-job engine contract.
    """
    user = await User.get(user_id)
    style_prompt = user.bake_style_prompt if user else None
    media_ctx = await _media_ctx(user_id)

    messages = await RawMessage.find(
        {"_id": {"$in": entry.source_messages}}
    ).sort("+created_at").to_list()

    if on_progress:
        await on_progress(0, 1, f"запис за {entry.date.strftime('%d.%m.%Y')}", "baking")

    entry.blocks = await _render_date_content(
        entry.date, messages, style_prompt, media_ctx, existing_blocks=None,
    )
    await _save_entry(entry)

    if on_progress:
        await on_progress(1, 1, "вилучення хайлайтів", "highlights")
    await _safe_extract_highlights([entry], user)
    return [entry]


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
        lines.append(f'- {shortcode} ({kind}) — контекст: "{desc}"')
    return "\n".join(lines)


async def _bake_date(
    user_id,
    entry_date: date,
    messages: list[RawMessage],
    style_prompt: str | None = None,
    media_ctx: dict | None = None,
) -> Entry:
    """Bake messages for a single date into an Entry (create or append)."""
    media_ctx = media_ctx or {}
    existing = await Entry.find_one({"user_id": user_id, "date": entry_date})

    blocks = await _render_date_content(
        entry_date, messages, style_prompt, media_ctx,
        existing_blocks=existing.blocks if existing else None,
    )

    if existing:
        existing.blocks = blocks
        existing.source_messages.extend([msg.id for msg in messages])
        return await _save_entry(existing)

    entry = Entry(
        user_id=user_id,
        date=entry_date,
        blocks=blocks,
        source_messages=[msg.id for msg in messages],
        version=1,
    )
    await entry.insert()
    return entry


async def _bake_new(
    messages: list[RawMessage], entry_date: date, style_prompt: str | None = None,
    registry_text: str = "", with_media: bool = False,
) -> list[dict]:
    """Generate a new diary entry (block list) from messages."""
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
                              temperature=0.7, max_tokens=8192, with_media=with_media)


async def _bake_append(
    existing_blocks: list, new_messages: list[RawMessage], entry_date: date,
    style_prompt: str | None = None, registry_text: str = "", with_media: bool = False,
) -> list[dict]:
    """Integrate new messages into an existing entry's block list."""
    formatted_date = entry_date.strftime("%d %B %Y")
    messages_text = _format_messages(new_messages) if new_messages else "(немає нових текстових повідомлень)"
    media_block = f"\n\n{registry_text}\n" if registry_text else ""
    existing_json = json.dumps(existing_blocks, ensure_ascii=False)
    user_prompt = (
        f"Дата: {formatted_date}\n\n"
        f"Існуючий запис (блоки JSON):\n{existing_json}\n\n"
        f"Нові повідомлення, які потрібно інтегрувати:\n\n{messages_text}\n"
        f"{media_block}\n"
        f"Доповни існуючий запис новою інформацією, зберігаючи наявні блоки. "
        f"Не дублюй те, що вже описано. Поверни ПОВНИЙ оновлений список блоків."
    )
    return await _call_claude(user_prompt, style_prompt=style_prompt,
                              temperature=0.5, max_tokens=8192, with_media=with_media)


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
    max_tokens: int = 8192,
    max_retries: int = 3,
    with_media: bool = False,
    model: str | None = None,
    effort: str | None = None,
) -> list[dict]:
    """Call Claude with structured outputs; return the (un-normalized) block list.

    Defaults to the bake model/effort; callers (e.g. the settings preview) may
    override ``model``/``effort`` to reuse this one structured-output path.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    system_prompt = build_system_prompt(style_prompt, with_media=with_media)
    schema = build_blocks_schema()
    model = model or settings.claude_model_bake
    effort = settings.claude_effort_bake if effort is None else effort
    cfg = output_config(effort=effort, schema=schema)

    last_error = None
    for attempt in range(max_retries):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                **cfg,
            )
            text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
            if text is None:
                raise ValueError("no text block in Claude response")
            data = json.loads(text)
            blocks = data.get("blocks")
            if not isinstance(blocks, list):
                raise ValueError("Claude response missing 'blocks' list")
            return blocks
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Bake Claude call failed (attempt %d/%d): %s", attempt + 1, max_retries, exc
            )
    raise last_error
