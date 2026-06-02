"""Shared test fixtures — in-memory MongoDB via mongomock."""

import pytest
import pytest_asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.models.user import User
from app.models.audio_job import AudioJob
from app.models.raw_message import RawMessage
from app.models.entry import Entry
from app.models.highlight import Highlight
from app.models.media_file import MediaFile
from app.models.bake_job import BakeJob

DOCUMENT_MODELS = [User, AudioJob, RawMessage, Entry, Highlight, MediaFile, BakeJob]


@pytest_asyncio.fixture(autouse=True)
async def init_db():
    """Initialize Beanie with mongomock for every test."""
    client = AsyncMongoMockClient()
    db = client["test_ai_diary"]
    await init_beanie(database=db, document_models=DOCUMENT_MODELS)
    yield
    for model in DOCUMENT_MODELS:
        await model.find_all().delete()


@pytest_asyncio.fixture
async def test_user():
    """Create a test user."""
    user = User(
        telegram_id=123456789,
        username="testuser",
        display_name="Test User",
    )
    await user.insert()
    return user
