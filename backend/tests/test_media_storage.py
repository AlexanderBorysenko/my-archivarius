"""Tests for the media storage service."""

import pytest

from app.models.media_file import MediaFile, MediaKind
from app.services import media_storage


@pytest.fixture(autouse=True)
def _tmp_media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage.settings, "media_files_path", str(tmp_path))


class TestShortcode:
    def test_format_and_uniqueness(self):
        codes = {media_storage.allocate_shortcode() for _ in range(200)}
        assert len(codes) == 200
        for c in codes:
            assert c.startswith("att_")
            assert all(ch.isalnum() or ch == "_" for ch in c)


class TestSave:
    def test_save_bytes_and_poster(self, tmp_path):
        path = media_storage.save_bytes("att_x", b"hello", ".jpg")
        assert path.endswith("att_x.jpg")
        with open(path, "rb") as f:
            assert f.read() == b"hello"

        poster = media_storage.save_poster("att_x", b"poster")
        assert poster.endswith("att_x_poster.jpg")


@pytest.mark.asyncio
class TestResolve:
    async def test_owner_gets_file(self, test_user):
        mf = MediaFile(user_id=test_user.id, shortcode="att_y", kind=MediaKind.PHOTO)
        await mf.insert()
        resolved = await media_storage.resolve("att_y", str(test_user.id))
        assert resolved is not None
        assert resolved.shortcode == "att_y"

    async def test_stranger_gets_none(self, test_user):
        mf = MediaFile(user_id=test_user.id, shortcode="att_z", kind=MediaKind.PHOTO)
        await mf.insert()
        assert await media_storage.resolve("att_z", "000000000000000000000000") is None

    async def test_missing_gets_none(self, test_user):
        assert await media_storage.resolve("att_nope", str(test_user.id)) is None
