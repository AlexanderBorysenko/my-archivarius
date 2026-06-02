"""Tests for Telegram media download + ingestion adapter."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services import telegram_files


@pytest.mark.asyncio
class TestDownload:
    async def test_two_step_download(self):
        get_resp = AsyncMock()
        get_resp.json = lambda: {"ok": True, "result": {"file_path": "photos/f.jpg"}}
        get_resp.raise_for_status = lambda: None

        file_resp = AsyncMock()
        file_resp.content = b"BINARY"
        file_resp.raise_for_status = lambda: None

        client = AsyncMock()
        client.get = AsyncMock(side_effect=[get_resp, file_resp])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.telegram_files.httpx.AsyncClient", return_value=client):
            data = await telegram_files.download_telegram_file("FID", "TOKEN")

        assert data == b"BINARY"


from types import SimpleNamespace

from app.models.media_file import MediaFile, MediaKind, MediaStatus
from app.services import media_ingest_telegram as ingest
from app.services import media_storage


@pytest.fixture(autouse=True)
def _tmp_media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage.settings, "media_files_path", str(tmp_path))


def _photo_message():
    photo = SimpleNamespace(file_id="PH", file_unique_id="u1", width=800, height=600, file_size=1234)
    return SimpleNamespace(photo=[photo], media_group_id=None, caption=None)


def _big_video_message():
    thumb = SimpleNamespace(file_id="THUMB")
    video = SimpleNamespace(
        file_id="VID", file_unique_id="u2", width=1920, height=1080,
        duration=120, mime_type="video/mp4", file_size=50 * 1024 * 1024, thumbnail=thumb,
    )
    return SimpleNamespace(video=video, media_group_id="g1", caption="вечір")


@pytest.mark.asyncio
class TestBuildMediaFile:
    async def test_photo(self, test_user):
        mf = await ingest.build_media_file(_photo_message(), test_user.id, MediaKind.PHOTO)
        assert mf.kind == MediaKind.PHOTO
        assert mf.source_file_id == "PH"
        assert mf.source_ref == "u1"
        assert mf.width == 800
        assert mf.status == MediaStatus.PENDING
        assert mf.shortcode.startswith("att_")


@pytest.mark.asyncio
class TestProcessDownload:
    async def test_ready(self, test_user):
        mf = await ingest.build_media_file(_photo_message(), test_user.id, MediaKind.PHOTO)
        with patch.object(ingest, "download_telegram_file", AsyncMock(return_value=b"IMG")):
            await ingest.process_media_download(mf, "TOKEN")
        refreshed = await MediaFile.get(mf.id)
        assert refreshed.status == MediaStatus.READY
        assert refreshed.storage_key.endswith(".jpg")

    async def test_oversize_video_poster_only(self, test_user):
        mf = await ingest.build_media_file(_big_video_message(), test_user.id, MediaKind.VIDEO)
        with patch.object(ingest, "download_telegram_file", AsyncMock(return_value=b"THUMBDATA")):
            await ingest.process_media_download(mf, "TOKEN")
        refreshed = await MediaFile.get(mf.id)
        assert refreshed.status == MediaStatus.OVERSIZE
        assert refreshed.storage_key is None
        assert refreshed.poster_key is not None

    async def test_failure_marks_failed(self, test_user):
        mf = await ingest.build_media_file(_photo_message(), test_user.id, MediaKind.PHOTO)
        with patch.object(ingest, "download_telegram_file", AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(RuntimeError):
                await ingest.process_media_download(mf, "TOKEN")
        refreshed = await MediaFile.get(mf.id)
        assert refreshed.status == MediaStatus.FAILED
        assert refreshed.attempts == 1
