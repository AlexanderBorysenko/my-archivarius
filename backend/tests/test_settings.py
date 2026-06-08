"""Tests for settings API — user preferences."""

import pytest
from unittest.mock import AsyncMock, patch

from app.models.user import User
from app.services.bake import build_system_prompt
from app.core.i18n import DEFAULT_STYLE_DISPLAY


@pytest.mark.asyncio
class TestGetSettings:
    async def test_returns_defaults_for_new_user(self, test_user):
        from app.api.settings import _get_settings_response
        result = _get_settings_response(test_user)
        assert result["bake_style_prompt"] is None
        assert result["default_style_prompt"] == DEFAULT_STYLE_DISPLAY["en"]

    async def test_returns_custom_prompt(self, test_user):
        test_user.bake_style_prompt = "Пиши коротко."
        await test_user.save()

        refreshed = await User.get(test_user.id)
        from app.api.settings import _get_settings_response
        result = _get_settings_response(refreshed)
        assert result["bake_style_prompt"] == "Пиши коротко."


@pytest.mark.asyncio
class TestUpdateSettings:
    async def test_save_custom_prompt(self, test_user):
        test_user.bake_style_prompt = "Пиши поетично."
        await test_user.save()

        refreshed = await User.get(test_user.id)
        assert refreshed.bake_style_prompt == "Пиши поетично."

    async def test_reset_to_default(self, test_user):
        test_user.bake_style_prompt = "Щось"
        await test_user.save()

        test_user.bake_style_prompt = None
        await test_user.save()

        refreshed = await User.get(test_user.id)
        assert refreshed.bake_style_prompt is None

    async def test_blank_string_resets_to_none(self, test_user):
        from app.api.settings import _normalize_style_prompt
        assert _normalize_style_prompt("") is None
        assert _normalize_style_prompt("   ") is None
        assert _normalize_style_prompt(None) is None
        assert _normalize_style_prompt("Коротко") == "Коротко"


@pytest.mark.asyncio
class TestSettingsLanguage:
    async def test_get_includes_language_and_localized_default(self, test_user):
        from app.api.settings import _get_settings_response
        result = _get_settings_response(test_user)
        assert result["language"] == "en"
        assert result["default_style_prompt"] == DEFAULT_STYLE_DISPLAY["en"]

    async def test_get_localizes_default_for_uk_user(self, test_user):
        test_user.language = "uk"
        await test_user.save()
        from app.api.settings import _get_settings_response
        result = _get_settings_response(test_user)
        assert result["language"] == "uk"
        assert result["default_style_prompt"] == DEFAULT_STYLE_DISPLAY["uk"]

    async def test_normalize_language_accepts_supported(self):
        from app.api.settings import _normalize_language
        assert _normalize_language("ru") == "ru"
        assert _normalize_language(None) is None

    async def test_normalize_language_rejects_unknown(self):
        from app.api.settings import _normalize_language
        with pytest.raises(ValueError):
            _normalize_language("de")

    async def test_language_only_patch_preserves_bake_style_prompt(self, test_user):
        """A language-only PATCH must NOT wipe an existing bake_style_prompt."""
        from app.api.settings import update_settings, UpdateSettingsRequest

        test_user.bake_style_prompt = "my custom style"
        await test_user.save()

        # Build the request with ONLY language set — bake_style_prompt must be
        # absent from model_fields_set so the partial-PATCH guard keeps the
        # existing value.
        body = UpdateSettingsRequest(language="uk")
        assert "bake_style_prompt" not in body.model_fields_set

        result = await update_settings(body=body, user=test_user)

        assert result["bake_style_prompt"] == "my custom style"
        assert result["language"] == "uk"
