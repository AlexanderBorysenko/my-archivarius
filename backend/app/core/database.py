from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings


async def init_db():
    """Initialize MongoDB connection and Beanie ODM."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]

    from app.models.user import User
    from app.models.raw_message import RawMessage
    from app.models.entry import Entry
    from app.models.highlight import Highlight
    from app.models.media_file import MediaFile
    from app.models.bake_job import BakeJob
    from app.models.inbound_event import InboundEvent

    await init_beanie(
        database=db,
        document_models=[User, RawMessage, Entry, Highlight, MediaFile, BakeJob, InboundEvent],
    )
