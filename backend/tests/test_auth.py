"""Tests for auth service — JWT tokens and Telegram verification."""

import hashlib
import hmac
import time
import pytest

from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_telegram_auth,
)
from app.core.config import settings


@pytest.mark.asyncio
class TestJWT:
    async def test_access_token_roundtrip(self):
        token = create_access_token("user-123")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    async def test_refresh_token_roundtrip(self):
        token = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"

    async def test_invalid_token_returns_none(self):
        assert decode_token("garbage.token.here") is None
        assert decode_token("") is None

    async def test_different_users_get_different_tokens(self):
        t1 = create_access_token("user-1")
        t2 = create_access_token("user-2")
        assert t1 != t2
        assert decode_token(t1)["sub"] == "user-1"
        assert decode_token(t2)["sub"] == "user-2"


@pytest.mark.asyncio
class TestTelegramAuth:
    def _make_auth_data(self, telegram_id=123456):
        """Build valid Telegram auth data with correct hash."""
        data = {
            "id": str(telegram_id),
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
            "auth_date": str(int(time.time())),
        }
        # Compute hash
        sorted_items = sorted(data.items())
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_items)
        secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        data["hash"] = computed
        return data

    async def test_valid_auth_passes(self):
        data = self._make_auth_data()
        assert verify_telegram_auth(data) is True

    async def test_tampered_data_fails(self):
        data = self._make_auth_data()
        data["first_name"] = "Hacker"
        assert verify_telegram_auth(data) is False

    async def test_missing_hash_fails(self):
        data = {"id": "123", "first_name": "Test", "auth_date": "1234567890"}
        assert verify_telegram_auth(data) is False


@pytest.mark.asyncio
async def test_authenticate_returns_language(monkeypatch):
    import app.services.auth as auth_mod

    monkeypatch.setattr(auth_mod, "verify_telegram_auth", lambda data: True)

    result = await auth_mod.authenticate_telegram(
        {"id": 555001, "first_name": "Lang", "last_name": "Test", "username": "langtest", "hash": "x"}
    )
    assert result["user"]["language"] == "en"
