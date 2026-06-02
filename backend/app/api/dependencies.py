"""Shared API dependencies — JWT auth, current user extraction."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId

from app.services.auth import decode_token
from app.models.user import User

security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Extract and validate user_id from JWT Bearer token.

    Returns the user_id string.
    """
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалідний або прострочений токен",
        )
    return payload["sub"]


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
) -> User:
    """Get the full User document for the authenticated user."""
    user = await User.get(ObjectId(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Користувача не знайдено",
        )
    return user


async def get_media_user_id(request: Request) -> str:
    """Authenticate a media request via the media_token cookie, falling back to
    a Bearer access token (for tests/API)."""
    token = request.cookies.get("media_token")
    if token:
        payload = decode_token(token)
        if payload and payload.get("type") == "media":
            return payload["sub"]

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_token(auth[7:])
        if payload and payload.get("type") == "access":
            return payload["sub"]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не авторизовано",
    )
