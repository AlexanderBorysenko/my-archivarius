import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.transcription import transcribe_audio


@pytest.mark.asyncio
@patch("app.services.transcription.AsyncOpenAI")
async def test_transcribe_does_not_force_language(mock_openai_cls, tmp_path):
    audio = tmp_path / "v.ogg"
    audio.write_bytes(b"fake-audio")

    mock_resp = MagicMock()
    mock_resp.text = "hello world"
    instance = MagicMock()
    instance.audio.transcriptions.create = AsyncMock(return_value=mock_resp)
    mock_openai_cls.return_value = instance

    result = await transcribe_audio(str(audio))

    assert result == "hello world"
    _, kwargs = instance.audio.transcriptions.create.call_args
    assert "language" not in kwargs  # auto-detect
