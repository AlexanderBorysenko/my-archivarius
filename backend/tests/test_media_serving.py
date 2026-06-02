"""Integration tests for the media serving endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.media_file import MediaFile, MediaKind, MediaStatus
from app.services.auth import create_access_token
from app.services import media_storage
from app.api.media import router as media_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage.settings, "media_files_path", str(tmp_path))
    app = FastAPI()
    app.include_router(media_router)
    return TestClient(app)


async def _ready_photo(user_id):
    path = media_storage.save_bytes("att_serve", b"IMAGEBYTES", ".jpg")
    mf = MediaFile(
        user_id=user_id, shortcode="att_serve", kind=MediaKind.PHOTO,
        status=MediaStatus.READY, storage_key=path, mime="image/jpeg",
    )
    await mf.insert()
    return mf


@pytest.mark.asyncio
class TestServing:
    async def test_owner_gets_bytes(self, client, test_user):
        await _ready_photo(test_user.id)
        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = client.get("/api/media/att_serve", headers=headers)
        assert resp.status_code == 200
        assert resp.content == b"IMAGEBYTES"

    async def test_stranger_gets_404(self, client, test_user):
        await _ready_photo(test_user.id)
        headers = {"Authorization": f"Bearer {create_access_token('000000000000000000000000')}"}
        resp = client.get("/api/media/att_serve", headers=headers)
        assert resp.status_code == 404

    async def test_no_auth_401(self, client, test_user):
        await _ready_photo(test_user.id)
        assert client.get("/api/media/att_serve").status_code == 401

    async def test_range_request(self, client, test_user):
        await _ready_photo(test_user.id)
        headers = {
            "Authorization": f"Bearer {create_access_token(str(test_user.id))}",
            "Range": "bytes=0-3",
        }
        resp = client.get("/api/media/att_serve", headers=headers)
        assert resp.status_code == 206
        assert resp.content == b"IMAG"
