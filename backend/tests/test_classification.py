"""Tests for classification service — date parsing and Claude API integration."""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.classification import classify_date, _parse_response, SYSTEM_PROMPT, DAY_NAMES_EN


class TestParseResponse:
    def test_valid_json(self):
        raw = '{"classified_date": "2026-04-22", "confidence": 0.95, "reasoning": "test"}'
        result = _parse_response(raw, date(2026, 4, 23))
        assert result["classified_date"] == date(2026, 4, 22)
        assert result["confidence"] == 0.95

    def test_json_with_code_fences(self):
        raw = '```json\n{"classified_date": "2026-04-22", "confidence": 0.9}\n```'
        result = _parse_response(raw, date(2026, 4, 23))
        assert result["classified_date"] == date(2026, 4, 22)

    def test_missing_date_raises(self):
        raw = '{"confidence": 0.9}'
        with pytest.raises(ValueError, match="Missing"):
            _parse_response(raw, date(2026, 4, 23))

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_response("not json at all", date(2026, 4, 23))


@pytest.mark.asyncio
class TestClassifyDate:
    @patch("app.services.classification.anthropic.AsyncAnthropic")
    async def test_successful_classification(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"classified_date": "2026-04-21", "confidence": 0.98}')]

        mock_instance = MagicMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_instance

        result = await classify_date(
            "Вчора була чудова погода",
            datetime(2026, 4, 22, 10, 30),
        )
        assert result == date(2026, 4, 21)

    @patch("app.services.classification.anthropic.AsyncAnthropic")
    async def test_fallback_on_api_error(self, mock_client_cls):
        import anthropic
        mock_instance = MagicMock()
        mock_instance.messages.create = AsyncMock(
            side_effect=anthropic.APIError(
                message="Server error",
                request=MagicMock(),
                body=None,
            )
        )
        mock_client_cls.return_value = mock_instance

        send_dt = datetime(2026, 4, 22, 10, 30)
        result = await classify_date("test", send_dt, max_retries=1)
        # Should fallback to send date
        assert result == date(2026, 4, 22)

    @patch("app.services.classification.anthropic.AsyncAnthropic")
    async def test_fallback_on_invalid_json(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not JSON")]

        mock_instance = MagicMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_instance

        send_dt = datetime(2026, 4, 22, 10, 30)
        result = await classify_date("test", send_dt, max_retries=1)
        assert result == date(2026, 4, 22)


class TestPromptIsLanguageAware:
    def test_mentions_three_languages(self):
        assert "Russian" in SYSTEM_PROMPT
        assert "Ukrainian" in SYSTEM_PROMPT
        assert "English" in SYSTEM_PROMPT

    def test_recognizes_russian_markers(self):
        assert "позавчера" in SYSTEM_PROMPT
        assert "дней назад" in SYSTEM_PROMPT

    def test_english_weekday_names(self):
        assert DAY_NAMES_EN[0] == "Monday"
        assert len(DAY_NAMES_EN) == 7
