"""Settings API — user preferences for bake style and future settings."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.dependencies import get_current_user, get_current_user_id
from app.core.config import settings as app_settings
from app.models.user import User
from app.services.bake import _call_claude
from app.services.blocks import blocks_to_text
from app.core.i18n import t, DEFAULT_STYLE_DISPLAY, SUPPORTED_LANGS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Settings"])

PREVIEW_SAMPLES = {
    "en": (
        "[09:00] (text): Woke up early, it's sunny outside. Good mood.\n"
        "[12:30] (voice): Met a friend for lunch, we talked about his new job. "
        "He says he's very happy, but the workload is heavy.\n"
        "[18:00] (text): Read a book in the evening, really gripping. I think I'll finish it tomorrow."
    ),
    "uk": (
        "[09:00] (text): Прокинувся рано, на вулиці сонячно. Настрій гарний.\n"
        "[12:30] (voice): Зустрівся з другом на обіді, обговорювали його нову роботу. "
        "Каже що дуже задоволений, але навантаження велике.\n"
        "[18:00] (text): Увечері читав книгу, дуже затягує. Думаю завтра дочитаю."
    ),
    "ru": (
        "[09:00] (text): Проснулся рано, на улице солнечно. Настроение хорошее.\n"
        "[12:30] (voice): Встретился с другом на обеде, обсуждали его новую работу. "
        "Говорит, что очень доволен, но нагрузка большая.\n"
        "[18:00] (text): Вечером читал книгу, очень затягивает. Думаю, завтра дочитаю."
    ),
}

PREVIEW_DATE = {"en": "22 April 2026", "uk": "22 квітня 2026", "ru": "22 апреля 2026"}

PREVIEW_INSTRUCTION = {
    "en": "Create a diary entry for this date.",
    "uk": "Створи щоденниковий запис за цю дату.",
    "ru": "Создай запись дневника за эту дату.",
}


def _get_settings_response(user: User) -> dict:
    lang = user.language or "en"
    return {
        "bake_style_prompt": user.bake_style_prompt,
        "default_style_prompt": DEFAULT_STYLE_DISPLAY.get(lang, DEFAULT_STYLE_DISPLAY["en"]),
        "language": lang,
    }


def _normalize_style_prompt(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in SUPPORTED_LANGS:
        raise ValueError(f"Unsupported language: {value}")
    return value


class UpdateSettingsRequest(BaseModel):
    bake_style_prompt: Optional[str] = None
    language: Optional[str] = None


class PreviewStyleRequest(BaseModel):
    style_prompt: Optional[str] = None


@router.get("")
async def get_settings(user: User = Depends(get_current_user)):
    return _get_settings_response(user)


@router.patch("")
async def update_settings(
    body: UpdateSettingsRequest,
    user: User = Depends(get_current_user),
):
    if "bake_style_prompt" in body.model_fields_set:
        user.bake_style_prompt = _normalize_style_prompt(body.bake_style_prompt)
    if body.language is not None:
        try:
            user.language = _normalize_language(body.language)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unsupported language")
    await user.save()
    return _get_settings_response(user)


@router.post("/preview-style")
async def preview_style(
    body: PreviewStyleRequest,
    user: User = Depends(get_current_user),
):
    lang = user.language or "en"
    sample = PREVIEW_SAMPLES.get(lang, PREVIEW_SAMPLES["en"])
    user_prompt = (
        f"Date: {PREVIEW_DATE.get(lang, PREVIEW_DATE['en'])}\n\n"
        "Raw messages (chronological):\n\n"
        f"{sample}\n\n"
        f"{PREVIEW_INSTRUCTION.get(lang, PREVIEW_INSTRUCTION['en'])}"
    )
    try:
        blocks = await _call_claude(
            user_prompt,
            style_prompt=_normalize_style_prompt(body.style_prompt),
            temperature=0.7,
            max_tokens=2048,
            model=app_settings.claude_model_preview,
            effort=app_settings.claude_effort_preview,
        )
    except Exception as exc:
        logger.error("Preview style failed: %s", exc)
        raise HTTPException(status_code=502, detail=t("preview_failed", lang))

    return {
        "preview": blocks_to_text(blocks),
        "sample_messages": sample.split("\n"),
    }
