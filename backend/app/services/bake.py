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
from app.core.i18n import LANG_NAMES, DEFAULT_LANG

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str, str], Awaitable[None]]
"""Async callback: (completed_steps, total_steps, current_label, phase)."""

CORE_RULES = """You are an editor of a personal diary. Your task is to transform raw messages (notes, voice transcriptions) into a coherent diary entry.

Mandatory rules:
1. PRESERVE all meaning — do not invent facts or add anything that was not there.
2. Fix grammar and transcription errors, but keep the author's voice and characteristic expressions.
3. Chronological order: if a sequence of events can be determined, preserve it.
4. If something is repeated (the same thing said in a text note and a voice note) — merge it, do not duplicate.
5. Write prose in "markdown"-type blocks (the text field) using normal Markdown: paragraphs, **bold**, lists.
6. Do not add any preface like "Here is your entry:" or explanations — return only the entry blocks.
7. LANGUAGE: Write the entry in the SAME language(s) the author used in the source messages. If the author mixes languages, preserve that mix and their phrasing and characteristic expressions — do not normalize to a single language. When extending an existing entry, match the language of that existing entry. Never translate the author's content into another language."""

BLOCKS_RULES = """Entry structure — an ordered list of blocks:
- "markdown" — prose (the text field). Structure the entry with headings `## Section title` (and `### Subtopic` where needed); each section is a separate topic or event of the day. Do NOT use `---` to separate topics — only headings.
- Split the prose into several markdown blocks so that media blocks can sit between paragraphs at contextually appropriate places."""

DEFAULT_STYLE = """Style: a personal diary — first person, natural, not overly formal."""

MEDIA_RULES = """Media blocks (when a media registry is provided):
- Place EVERY file from the registry at a contextually appropriate spot. "descriptive" is only a hint about where it fits; do NOT output it into the text.
- 2+ related PHOTOS (one event/location) → a "gallery" block (images: list of shortcodes; caption: a short caption).
- A single media item (photo OR video) → a "figure" block (media: shortcode; width ∈ {25,33,50,100}; align ∈ {left,right,center,full}; caption):
  • align left/right (width 25/33/50) — the photo sits to the side and the text wraps around it (float).
  • width 50 + align center — a meaningful frame on its own, centered.
  • width 100 + align full — a key or wide frame / video at full width.
- ORDER of floated photos (align left/right) is critical: put such a "figure" BEFORE the markdown block whose text describes it (the float only affects text AFTER the photo in the block list; placing the photo after the text breaks the wrap). The float resets at every heading (`##`/`###`), so keep a floated photo within its section: after the section heading, before its prose. For align center/full photos order does not matter — place them between paragraphs where appropriate.
- Write the caption yourself, short. Do not use the same shortcode twice. A gallery is for photos only; video is always a separate "figure"."""


def build_system_prompt(
    user_style: str | None,
    with_media: bool = False,
    fallback_lang: str | None = None,
) -> str:
    style = user_style.strip() if user_style and user_style.strip() else None
    prompt = f"{CORE_RULES}\n\n{BLOCKS_RULES}\n\n{style if style else DEFAULT_STYLE}"
    if with_media:
        prompt = f"{prompt}\n\n{MEDIA_RULES}"
    if fallback_lang:
        lang_name = LANG_NAMES.get(fallback_lang, LANG_NAMES[DEFAULT_LANG])
        prompt = (
            f"{prompt}\n\nThe author provided no text for this entry. "
            f"Write it in {lang_name}."
        )
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
    lang: str = DEFAULT_LANG,
) -> list[dict]:
    """Produce the finished block list for one date from its messages (no DB writes)."""
    narrative, media = _split_messages(messages)
    registry = await _build_media_registry(media)
    shortcodes = [e[0] for e in registry]
    registry_text = _format_media_registry(registry) if registry else ""
    fallback_lang = None if narrative else lang

    if existing_blocks is None:
        raw = await _bake_new(narrative, entry_date, style_prompt, registry_text, bool(registry), fallback_lang)
    else:
        raw = await _bake_append(
            existing_blocks, narrative, entry_date, style_prompt, registry_text, bool(registry), fallback_lang
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
    lang = user.language if user else DEFAULT_LANG
    media_ctx = await _media_ctx(user_id)

    by_date: dict[date, list[RawMessage]] = defaultdict(list)
    for msg in messages:
        by_date[msg.classified_date].append(msg)

    sorted_dates = sorted(by_date.keys())
    total = len(sorted_dates)

    entries = []
    for i, entry_date in enumerate(sorted_dates):
        if on_progress:
            await on_progress(i, total, f"entry for {entry_date.strftime('%d.%m.%Y')}", "baking")

        date_messages = by_date[entry_date]
        date_messages.sort(key=lambda m: m.created_at or datetime.min)

        entry = await _bake_date(user_id, entry_date, date_messages, style_prompt, media_ctx, lang)
        entries.append(entry)

        for msg in date_messages:
            msg.status = MessageStatus.BAKED
            await msg.save()

    if on_progress:
        await on_progress(total, total, "extracting highlights", "highlights")

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
    lang = user.language if user else DEFAULT_LANG
    media_ctx = await _media_ctx(user_id)

    messages = await RawMessage.find(
        {"_id": {"$in": entry.source_messages}}
    ).sort("+created_at").to_list()

    if on_progress:
        await on_progress(0, 1, f"entry for {entry.date.strftime('%d.%m.%Y')}", "baking")

    entry.blocks = await _render_date_content(
        entry.date, messages, style_prompt, media_ctx, existing_blocks=None, lang=lang,
    )
    await _save_entry(entry)

    if on_progress:
        await on_progress(1, 1, "extracting highlights", "highlights")
    await _safe_extract_highlights([entry], user)
    return [entry]


async def _build_media_registry(media_messages: list[RawMessage]) -> list[tuple[str, str, str]]:
    """Return (shortcode, kind, descriptive) tuples in chronological order."""
    entries: list[tuple[str, str, str]] = []
    for m in sorted(media_messages, key=lambda x: x.created_at or datetime.min):
        files = await MediaFile.find({"_id": {"$in": m.media_file_ids}}).to_list()
        desc = m.descriptive or "no description"
        for f in files:
            entries.append((f.shortcode, f.kind.value, desc))
    return entries


def _format_media_registry(entries: list[tuple[str, str, str]]) -> str:
    lines = ["Media registry (descriptive — a hint only, do NOT include it in the text):"]
    for shortcode, kind, desc in entries:
        lines.append(f'- {shortcode} ({kind}) — context: "{desc}"')
    return "\n".join(lines)


async def _bake_date(
    user_id,
    entry_date: date,
    messages: list[RawMessage],
    style_prompt: str | None = None,
    media_ctx: dict | None = None,
    lang: str = DEFAULT_LANG,
) -> Entry:
    """Bake messages for a single date into an Entry (create or append)."""
    media_ctx = media_ctx or {}
    existing = await Entry.find_one({"user_id": user_id, "date": entry_date})

    blocks = await _render_date_content(
        entry_date, messages, style_prompt, media_ctx,
        existing_blocks=existing.blocks if existing else None, lang=lang,
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
    registry_text: str = "", with_media: bool = False, fallback_lang: str | None = None,
) -> list[dict]:
    """Generate a new diary entry (block list) from messages."""
    formatted_date = entry_date.strftime("%d %B %Y")
    messages_text = _format_messages(messages) if messages else "(no text messages)"
    media_block = f"\n\n{registry_text}\n" if registry_text else ""
    user_prompt = (
        f"Date: {formatted_date}\n\n"
        f"Raw messages (chronological):\n\n{messages_text}\n"
        f"{media_block}\n"
        f"Create a diary entry for this date."
    )
    return await _call_claude(user_prompt, style_prompt=style_prompt,
                              temperature=0.7, max_tokens=8192, with_media=with_media,
                              fallback_lang=fallback_lang)


async def _bake_append(
    existing_blocks: list, new_messages: list[RawMessage], entry_date: date,
    style_prompt: str | None = None, registry_text: str = "", with_media: bool = False,
    fallback_lang: str | None = None,
) -> list[dict]:
    """Integrate new messages into an existing entry's block list."""
    formatted_date = entry_date.strftime("%d %B %Y")
    messages_text = _format_messages(new_messages) if new_messages else "(no new text messages)"
    media_block = f"\n\n{registry_text}\n" if registry_text else ""
    existing_json = json.dumps(existing_blocks, ensure_ascii=False)
    user_prompt = (
        f"Date: {formatted_date}\n\n"
        f"Existing entry (blocks JSON):\n{existing_json}\n\n"
        f"New messages to integrate:\n\n{messages_text}\n"
        f"{media_block}\n"
        f"Extend the existing entry with the new information, keeping the existing blocks. "
        f"Do not duplicate what is already described. Return the FULL updated list of blocks."
    )
    return await _call_claude(user_prompt, style_prompt=style_prompt,
                              temperature=0.5, max_tokens=8192, with_media=with_media,
                              fallback_lang=fallback_lang)


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
    fallback_lang: str | None = None,
) -> list[dict]:
    """Call Claude with structured outputs; return the (un-normalized) block list.

    Defaults to the bake model/effort; callers (e.g. the settings preview) may
    override ``model``/``effort`` to reuse this one structured-output path.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    system_prompt = build_system_prompt(style_prompt, with_media=with_media, fallback_lang=fallback_lang)
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
