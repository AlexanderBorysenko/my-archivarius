"""Tests for the channel-pure voice pipeline functions."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services import transcription


@pytest.mark.asyncio
class TestDownloadToRef:
    async def test_writes_neutral_file_and_returns_ref(self, tmp_path, monkeypatch):
        monkeypatch.setattr(transcription, "AUDIO_DIR", tmp_path)
        with patch.object(
            transcription, "download_telegram_file", AsyncMock(return_value=b"OGGDATA")
        ):
            ref = await transcription.download_voice_to_ref("FID-9", "TOKEN")

        assert Path(ref).exists()
        assert Path(ref).read_bytes() == b"OGGDATA"


@pytest.mark.asyncio
class TestTranscribeAudio:
    async def test_returns_text(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"x")

        fake_resp = type("R", (), {"text": "  привіт світ  "})()
        fake_client = AsyncMock()
        fake_client.audio.transcriptions.create = AsyncMock(return_value=fake_resp)

        with patch.object(transcription, "AsyncOpenAI", return_value=fake_client):
            text = await transcription.transcribe_audio(str(audio))

        assert text == "привіт світ"

    async def test_empty_transcription_raises(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"x")

        fake_resp = type("R", (), {"text": "   "})()
        fake_client = AsyncMock()
        fake_client.audio.transcriptions.create = AsyncMock(return_value=fake_resp)

        with patch.object(transcription, "AsyncOpenAI", return_value=fake_client):
            with pytest.raises(ValueError):
                await transcription.transcribe_audio(str(audio))
