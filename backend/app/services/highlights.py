"""Highlights extraction service — identifies ideas, stories, moods, insights from entries."""

import json
import logging
from datetime import datetime
from typing import Optional

import anthropic

from app.core.config import settings
from app.models.entry import Entry
from app.models.highlight import Highlight
from app.models.user import User
from app.services.blocks import blocks_to_text
from app.services.llm import output_config

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY_PROMPTS = {
    "idea": "creative thoughts, plans, intentions, business ideas",
    "story": "notable events, trips, meetings, stories worth remembering",
    "mood": "emotional state, reflection, psychological observations",
    "insight": "conclusions, realizations, 'aha' moments, life lessons, shifts in worldview, new understanding of oneself or life",
}

SYSTEM_PROMPT_TEMPLATE = """You are an analyst of a personal diary. Your task is to extract meaningful highlights from the entry text.

Highlight categories:
{categories_section}

Rules:
1. A highlight must be self-contained — understandable without the rest of the entry.
2. Do not create highlights from mundane things ("had breakfast", "went to work").
3. One entry may have 0-5 highlights. If nothing is meaningful — return an empty array.
4. Title — short and pithy (3-7 words).
5. Content — a concise summary (1-3 sentences) conveying the essence.
6. Use ONLY the categories from the list above, and emit the category value EXACTLY as one of the listed category names — do not translate category names.
7. LANGUAGE: produce each highlight's title and content in the SAME language as the diary entry; preserve the author's phrasing; never translate.

Response format (JSON):
{{"highlights": [{{"title": "...", "category": "...", "content": "..."}}]}}

Reply with ONLY JSON."""


def _build_system_prompt(user: Optional[User] = None) -> str:
    """Build system prompt using the user's category configuration."""
    lines = []

    for name, default_prompt in DEFAULT_CATEGORY_PROMPTS.items():
        prompt_text = default_prompt
        enabled = True

        if user:
            override = next((o for o in (user.category_overrides or []) if o.name == name), None)
            if override:
                enabled = override.enabled
                if override.prompt:
                    prompt_text = override.prompt

        if enabled:
            lines.append(f"- **{name}** — {prompt_text}")

    if user:
        for cat in (user.custom_categories or []):
            if cat.enabled and cat.prompt:
                lines.append(f"- **{cat.name}** — {cat.prompt}")

    if not lines:
        lines.append("- **insight** — anything meaningful, worth attention")

    return SYSTEM_PROMPT_TEMPLATE.format(categories_section="\n".join(lines))


async def extract_highlights(entry: Entry, user: Optional[User] = None) -> list[Highlight]:
    """Extract highlights from a diary entry using Claude API.

    Deletes any previous highlights for this entry before creating new ones.
    """
    deleted = await Highlight.find({"source_entries": entry.id}).delete()
    if deleted and deleted.deleted_count:
        logger.info("Deleted %d old highlights for entry %s before re-extraction", deleted.deleted_count, entry.id)

    system_prompt = _build_system_prompt(user)

    formatted_date = entry.date.strftime("%d %B %Y")
    user_prompt = (
        f"Entry date: {formatted_date}\n\n"
        f"Entry text:\n---\n{blocks_to_text(entry.blocks)}\n---\n\n"
        f"Extract highlights from this entry."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    last_error = None
    for attempt in range(3):
        try:
            response = await client.messages.create(
                model=settings.claude_model_highlights,
                max_tokens=2048,
                temperature=0.3,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                **output_config(effort=settings.claude_effort_highlights),
            )

            raw_text = response.content[0].text.strip()
            data = _parse_response(raw_text)

            highlights = []
            for item in data.get("highlights", []):
                h = Highlight(
                    user_id=entry.user_id,
                    title=item["title"],
                    category=item["category"],
                    content=item["content"],
                    source_entries=[entry.id],
                    date_range={"from_date": entry.date, "to_date": entry.date},
                )
                await h.insert()
                highlights.append(h)

            entry.highlights_checked = True
            entry.updated_at = datetime.utcnow()
            await entry.save()

            logger.info(
                "Extracted %d highlights from entry %s",
                len(highlights),
                entry.id,
            )
            return highlights

        except anthropic.RateLimitError:
            import asyncio

            wait = 2 ** (attempt + 1)
            logger.warning("Rate limit hit, retrying in %ds", wait)
            await asyncio.sleep(wait)
            last_error = "rate_limit"

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Invalid response on attempt %d: %s", attempt + 1, exc)
            last_error = exc

        except anthropic.APIError as exc:
            logger.error("Claude API error: %s", exc)
            last_error = exc
            break

    logger.error("Highlights extraction failed (%s)", last_error)
    return []


def _parse_response(raw_text: str) -> dict:
    """Parse JSON response, stripping markdown fences if present."""
    text = raw_text
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)

    return json.loads(text)


async def extract_highlights_for_entries(entries: list[Entry], user: Optional[User] = None) -> list[Highlight]:
    """Extract highlights for multiple entries."""
    all_highlights = []
    for entry in entries:
        if not entry.highlights_checked:
            highlights = await extract_highlights(entry, user)
            all_highlights.extend(highlights)
    return all_highlights
