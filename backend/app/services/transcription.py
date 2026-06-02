"""Audio transcription service — downloads voice from Telegram, transcribes via Whisper."""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.audio_job import AudioJob, AudioJobStatus
from app.models.raw_message import RawMessage, SourceType, MessageStatus
from app.services.classification import classify_date
from app.services.telegram_files import download_telegram_file

logger = logging.getLogger(__name__)

AUDIO_DIR = Path(settings.audio_files_path)


async def process_audio_job(job: AudioJob, bot_token: str) -> None:
    """Full pipeline for a single audio job: download → transcribe → classify → save.

    Args:
        job: The AudioJob document to process.
        bot_token: Telegram bot token for downloading files.
    """
    try:
        # --- Step 1: Download ---
        job.status = AudioJobStatus.DOWNLOADING
        job.updated_at = datetime.utcnow()
        await job.save()

        file_path = await _download_voice(job.file_id, bot_token)
        job.file_path = str(file_path)

        # --- Step 2: Transcribe ---
        job.status = AudioJobStatus.TRANSCRIBING
        job.updated_at = datetime.utcnow()
        await job.save()

        transcription = await _transcribe(file_path)
        job.transcription = transcription

        # --- Step 3: Classify date ---
        send_dt = job.created_at or datetime.utcnow()
        try:
            classified = await classify_date(transcription, send_dt)
        except Exception:
            classified = send_dt.date()

        # --- Step 4: Create RawMessage ---
        raw_msg = RawMessage(
            user_id=job.user_id,
            source_type=SourceType.VOICE,
            content=transcription,
            telegram_message_id=job.telegram_message_id,
            audio_duration=job.duration,
            classified_date=classified,
            status=MessageStatus.PENDING,
        )
        await raw_msg.insert()

        job.raw_message_id = raw_msg.id
        job.status = AudioJobStatus.COMPLETED
        job.updated_at = datetime.utcnow()
        await job.save()

        logger.info("Audio job %s completed: %d chars transcribed", job.id, len(transcription))

    except Exception as exc:
        job.status = AudioJobStatus.ERROR
        job.error_message = str(exc)[:500]
        job.attempts = (job.attempts or 0) + 1
        job.updated_at = datetime.utcnow()
        await job.save()
        logger.error("Audio job %s failed: %s", job.id, exc)
        raise


async def _download_voice(file_id: str, bot_token: str) -> Path:
    """Download a voice file from Telegram and save locally."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    data = await download_telegram_file(file_id, bot_token)
    local_path = AUDIO_DIR / f"{file_id}.ogg"
    local_path.write_bytes(data)
    logger.info("Downloaded voice file: %s (%d bytes)", local_path.name, len(data))
    return local_path


async def _transcribe(file_path: Path) -> str:
    """Transcribe an audio file using OpenAI Whisper API.

    Returns the transcribed text.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    with open(file_path, "rb") as audio_file:
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="uk",  # Ukrainian
        )

    text = response.text.strip()
    if not text:
        raise ValueError("Whisper returned empty transcription")

    return text


async def retry_failed_jobs(bot_token: str, max_attempts: int = 3) -> int:
    """Find and retry failed audio jobs that haven't exceeded max attempts.

    Returns the number of jobs retried.
    """
    failed_jobs = await AudioJob.find(
        {
            "status": AudioJobStatus.ERROR,
            "attempts": {"$lt": max_attempts},
        }
    ).to_list()

    retried = 0
    for job in failed_jobs:
        try:
            await process_audio_job(job, bot_token)
            retried += 1
        except Exception:
            pass  # Error already logged inside process_audio_job

    return retried
