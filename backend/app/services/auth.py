"""Auth service — JWT token management and Telegram auth verification."""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


def create_access_token(user_id: str) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token."""
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_media_token(user_id: str) -> str:
    """Token for cookie-based media serving. Session-length so <img> requests
    don't break when the short access token expires."""
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {"sub": user_id, "exp": expire, "type": "media"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token.

    Returns the payload dict or None if invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None


def verify_telegram_auth(data: dict) -> bool:
    """Verify Telegram Login Widget auth data.

    The data dict should contain: id, first_name, last_name, username,
    photo_url, auth_date, hash.

    Verification: https://core.telegram.org/widgets/login#checking-authorization
    """
    check_hash = data.pop("hash", None)
    if not check_hash:
        return False

    # Build the data-check-string
    sorted_items = sorted(data.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_items)

    # Secret key = SHA256 of bot token
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    return computed_hash == check_hash


async def authenticate_telegram(auth_data: dict) -> dict:
    """Full Telegram auth flow: verify → find/create user → issue tokens.

    Returns dict with access_token, refresh_token, user info.
    """
    if not verify_telegram_auth(auth_data.copy()):
        raise ValueError("Invalid Telegram auth data")

    telegram_id = int(auth_data["id"])

    # Find or create user
    user = await User.find_one({"telegram_id": telegram_id})
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=auth_data.get("username"),
            display_name=(
                f"{auth_data.get('first_name', '')} {auth_data.get('last_name', '')}".strip()
                or str(telegram_id)
            ),
        )
        await user.insert()

    user_id = str(user.id)
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "display_name": user.display_name,
        },
    }
