"""Tests for highlights extraction service."""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.entry import Entry
from app.models.highlight import Highlight
from app.services.highlights import extract_highlights, _parse_response, _build_system_prompt, SYSTEM_PROMPT_TEMPLATE
from app.models.user import CustomCategory


class TestParseResponse:
    def test_valid_json(self):
        raw = '{"highlights": [{"title": "Test", "category": "idea", "content": "Test content"}]}'
        result = _parse_response(raw)
        assert len(result["highlights"]) == 1
        assert result["highlights"][0]["title"] == "Test"

    def test_empty_highlights(self):
        raw = '{"highlights": []}'
        result = _parse_response(raw)
        assert result["highlights"] == []

    def test_json_with_code_fences(self):
        raw = '```json\n{"highlights": []}\n```'
        result = _parse_response(raw)
        assert result["highlights"] == []


class TestBuildSystemPrompt:
    def test_without_custom_categories(self):
        prompt = _build_system_prompt(None)
        assert "idea" in prompt
        assert "story" in prompt
        assert "Додаткові категорії" not in prompt

    def test_with_custom_categories(self):
        cats = [CustomCategory(name="health", description="Здоров'я та фітнес")]
        prompt = _build_system_prompt(cats)
        assert "health" in prompt
        assert "Здоров'я та фітнес" in prompt
        assert "Додаткові категорії" in prompt


class TestHighlightPromptLanguage:
    def test_template_has_mirror_language_rule(self):
        assert "same language" in SYSTEM_PROMPT_TEMPLATE.lower()

    def test_template_keeps_category_names_untranslated(self):
        assert "do not translate category names" in SYSTEM_PROMPT_TEMPLATE.lower()

    def test_built_prompt_lists_default_categories(self):
        prompt = _build_system_prompt(None)
        assert "idea" in prompt and "insight" in prompt


@pytest.mark.asyncio
class TestExtractHighlights:
    @patch("app.services.highlights.anthropic.AsyncAnthropic")
    async def test_extracts_highlights(self, mock_client_cls, test_user):
        response_json = '{"highlights": [{"title": "Ідея стартапу", "category": "idea", "content": "Створити AI щоденник"}]}'
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=response_json)]
        mock_instance = MagicMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_instance

        entry = Entry(
            user_id=test_user.id,
            date=date(2026, 4, 22),
            blocks=[{"type": "markdown", "text": "Сьогодні придумав ідею AI щоденника."}],
            source_messages=[],
            version=1,
        )
        await entry.insert()

        highlights = await extract_highlights(entry)

        assert len(highlights) == 1
        assert highlights[0].title == "Ідея стартапу"
        assert highlights[0].category == "idea"

        # Check entry marked as checked
        updated = await Entry.get(entry.id)
        assert updated.highlights_checked is True

    @patch("app.services.highlights.anthropic.AsyncAnthropic")
    async def test_no_highlights_for_mundane_entry(self, mock_client_cls, test_user):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"highlights": []}')]
        mock_instance = MagicMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_instance

        entry = Entry(
            user_id=test_user.id,
            date=date(2026, 4, 22),
            blocks=[{"type": "markdown", "text": "Звичайний день. Працював, пообідав."}],
            source_messages=[],
            version=1,
        )
        await entry.insert()

        highlights = await extract_highlights(entry)
        assert len(highlights) == 0
