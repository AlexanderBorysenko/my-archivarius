"""Tests for media token creation and the media auth dependency."""

import pytest
from unittest.mock import MagicMock

from app.services.auth import create_media_token, create_access_token, decode_token
from app.api.dependencies import get_media_user_id


def _request(cookies=None, auth_header=None):
    req = MagicMock()
    req.cookies = cookies or {}
    req.headers = {"Authorization": auth_header} if auth_header else {}
    return req


class TestMediaToken:
    def test_type_is_media(self):
        payload = decode_token(create_media_token("user-1"))
        assert payload["type"] == "media"
        assert payload["sub"] == "user-1"


@pytest.mark.asyncio
class TestMediaDependency:
    async def test_cookie_accepted(self):
        req = _request(cookies={"media_token": create_media_token("u-cookie")})
        assert await get_media_user_id(req) == "u-cookie"

    async def test_bearer_fallback(self):
        req = _request(auth_header=f"Bearer {create_access_token('u-bearer')}")
        assert await get_media_user_id(req) == "u-bearer"

    async def test_access_token_in_cookie_rejected(self):
        # an access token in the media cookie must NOT be accepted
        req = _request(cookies={"media_token": create_access_token("u-x")})
        with pytest.raises(Exception):
            await get_media_user_id(req)

    async def test_no_creds_raises(self):
        with pytest.raises(Exception):
            await get_media_user_id(_request())
