"""Protected media serving — owner-only, Range-enabled."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.dependencies import get_media_user_id
from app.models.media_file import MediaStatus
from app.services.media_storage import resolve
from app.core.i18n import t, DEFAULT_LANG

router = APIRouter(prefix="/api/media", tags=["Media"])


@router.get("/{shortcode}")
async def get_media(shortcode: str, user_id: str = Depends(get_media_user_id)):
    mf = await resolve(shortcode, user_id)
    if not mf:
        raise HTTPException(status_code=404, detail=t("media_not_found", DEFAULT_LANG))
    if mf.status != MediaStatus.READY or not mf.storage_key:
        raise HTTPException(status_code=409, detail=t("file_unavailable", DEFAULT_LANG))
    return FileResponse(mf.storage_key, media_type=mf.mime or "application/octet-stream")


@router.get("/{shortcode}/poster")
async def get_media_poster(shortcode: str, user_id: str = Depends(get_media_user_id)):
    mf = await resolve(shortcode, user_id)
    if not mf or not mf.poster_key:
        raise HTTPException(status_code=404, detail=t("poster_not_found", DEFAULT_LANG))
    return FileResponse(mf.poster_key, media_type="image/jpeg")
