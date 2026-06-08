"""Auth endpoints — Telegram Login Widget and JWT refresh."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.core.config import settings
from app.services.auth import (
    authenticate_telegram, decode_token, create_access_token, create_media_token,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])

MEDIA_COOKIE_MAX_AGE = settings.jwt_refresh_token_expire_days * 24 * 3600


def _set_media_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key="media_token",
        value=create_media_token(user_id),
        max_age=MEDIA_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api/media",
    )


class TelegramAuthRequest(BaseModel):
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str = ""
    photo_url: str = ""
    auth_date: int
    hash: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/telegram")
async def telegram_auth(body: TelegramAuthRequest, response: Response):
    try:
        result = await authenticate_telegram(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    _set_media_cookie(response, result["user"]["id"])
    return result


@router.post("/refresh")
async def refresh_token(body: RefreshRequest, response: Response):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload["sub"]
    _set_media_cookie(response, user_id)
    return {
        "access_token": create_access_token(user_id),
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        "media_token", path="/api/media",
        samesite="strict", secure=settings.cookie_secure,
    )
    return {"ok": True}
