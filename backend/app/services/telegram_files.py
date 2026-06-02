"""Shared Telegram Bot API file download (two-step getFile → CDN)."""

import logging

import httpx

logger = logging.getLogger(__name__)


async def download_telegram_file(file_id: str, bot_token: str) -> bytes:
    """Download a Telegram file by file_id. Returns the raw bytes.

    Raises on HTTP errors or a non-ok getFile response.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": file_id},
            timeout=30,
        )
        resp.raise_for_status()
        info = resp.json()
        if not info.get("ok"):
            raise RuntimeError(f"Telegram getFile failed: {info}")

        file_path = info["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        resp = await client.get(download_url, timeout=60)
        resp.raise_for_status()
        return resp.content
