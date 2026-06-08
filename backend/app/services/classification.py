"""Date classification service — determines which date a message belongs to."""

import json
import logging
from datetime import date, datetime

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an assistant that classifies diary messages. Your task is to determine which date a message belongs to.

Rules:
1. If the message describes events "today" or has no time markers — the date = the send date.
2. If there are relative markers — compute the date relative to the send date:
   - "yesterday" / "вчора" / "вчера" → send date minus 1 day
   - "the day before yesterday" / "позавчора" / "позавчера" → minus 2 days
   - "N days ago" / "N днів тому" / "N дней назад" / "N дней тому назад" → minus N days
   - "last week" / "минулого тижня" / "на прошлой неделе" → minus 7 days (or the matching weekday)
   - "last month" / "минулого місяця" / "в прошлом месяце" → minus ~30 days
3. If there is a specific date ("April 15", "15 квітня", "on Monday", "в понедельник") — determine the absolute date. For weekdays choose the most recent past such day.
4. If the message contains events from different dates — choose the main date (the one with the most text about it).
5. IMPORTANT: messages may be in Ukrainian, English, or Russian, or mixed. Recognize time markers in all of these languages.

Reply with ONLY JSON in this format:
{"classified_date": "YYYY-MM-DD", "confidence": "high|medium|low"}"""

DAY_NAMES_EN = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


async def classify_date(
    message_content: str,
    send_datetime: datetime,
    max_retries: int = 3,
) -> date:
    """Classify which date a message belongs to using Claude API.

    Args:
        message_content: Text of the message.
        send_datetime: When the message was sent (UTC).
        max_retries: Number of retry attempts on failure.

    Returns:
        The classified date.
    """
    send_date = send_datetime.strftime("%Y-%m-%d")
    day_of_week = DAY_NAMES_EN[send_datetime.weekday()]
    send_time = send_datetime.strftime("%H:%M")

    user_prompt = (
        f"Send date: {send_date} ({day_of_week})\n"
        f"Current time: {send_time}\n\n"
        f'Message:\n"{message_content}"\n\n'
        f"Determine the date this message belongs to."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    last_error = None
    for attempt in range(max_retries):
        try:
            response = await client.messages.create(
                model=settings.claude_model_classification,
                max_tokens=256,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            raw_text = response.content[0].text.strip()
            result = _parse_response(raw_text, send_datetime.date())
            logger.info(
                "Classified message date: %s (confidence: %s)",
                result["classified_date"],
                result.get("confidence"),
            )
            return result["classified_date"]

        except anthropic.RateLimitError:
            import asyncio

            wait = 2 ** (attempt + 1)
            logger.warning("Rate limit hit, retrying in %ds (attempt %d)", wait, attempt + 1)
            await asyncio.sleep(wait)
            last_error = "rate_limit"

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Invalid response on attempt %d: %s", attempt + 1, exc)
            last_error = exc
            # (system prompt already requires JSON-only output)

        except anthropic.APIError as exc:
            logger.error("Claude API error: %s", exc)
            last_error = exc
            break

    # Fallback: use the send date
    logger.warning(
        "Classification failed after %d attempts (%s), falling back to send date",
        max_retries,
        last_error,
    )
    return send_datetime.date()


def _parse_response(raw_text: str, fallback_date: date) -> dict:
    """Parse the JSON response from Claude.

    Returns dict with 'classified_date' (date object), 'confidence', 'reasoning'.
    """
    # Strip markdown code fences if present
    text = raw_text
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)

    data = json.loads(text)

    classified_str = data.get("classified_date")
    if not classified_str:
        raise ValueError("Missing 'classified_date' in response")

    classified = date.fromisoformat(classified_str)

    return {
        "classified_date": classified,
        "confidence": data.get("confidence"),
        "reasoning": data.get("reasoning"),
    }
