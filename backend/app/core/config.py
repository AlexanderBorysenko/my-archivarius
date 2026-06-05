from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MongoDB
    mongodb_url: str = "mongodb://mongodb:27017"
    mongodb_db_name: str = "ai_diary"

    # Telegram Bot
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Whisper API
    openai_api_key: str = ""

    # JWT
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # Audio
    audio_files_path: str = "/app/audio_files"

    # Media
    media_files_path: str = "/app/media_files"
    media_max_upload_bytes: int = 25 * 1024 * 1024  # 25 MB web-upload cap

    # Bake
    bake_stale_seconds: int = 300

    # Inbound worker queue
    worker_concurrency: int = 4
    worker_max_attempts: int = 3
    worker_poll_seconds: float = 5.0
    worker_lease_stale_seconds: int = 300

    # Cookies (set COOKIE_SECURE=false for local http dev)
    cookie_secure: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
