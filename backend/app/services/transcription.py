"""Audio transcription service — downloads voice from Telegram, transcribes via Whisper."""

import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.telegram_files import download_telegram_file

logger = logging.getLogger(__name__)

AUDIO_DIR = Path(settings.audio_files_path)


async def download_voice_to_ref(file_id: str, bot_token: str) -> str:
    """Download a Telegram voice file to neutral local storage. Returns the path (audio_ref).

    Channel knowledge (bot_token) lives here, in the adapter-facing helper — the worker
    receives only the returned neutral ref.
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    data = await download_telegram_file(file_id, bot_token)
    local_path = AUDIO_DIR / f"{file_id}.ogg"
    local_path.write_bytes(data)
    logger.info("Downloaded voice file: %s (%d bytes)", local_path.name, len(data))
    return str(local_path)


async def transcribe_audio(audio_ref: str) -> str:
    """Transcribe a neutral audio path via Whisper. Channel-free, Mongo-free, pure I/O.

    Returns the transcribed text; raises ValueError on an empty transcription.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    with open(audio_ref, "rb") as audio_file:
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    text = response.text.strip()
    if not text:
        raise ValueError("Whisper returned empty transcription")
    return text
