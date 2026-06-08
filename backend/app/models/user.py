from datetime import datetime
from typing import Literal, Optional

from beanie import Document, Indexed
from pydantic import BaseModel, Field


class CustomCategory(BaseModel):
    """User-defined highlight category."""

    name: str
    description: str
    prompt: str = ""
    icon: Optional[str] = None
    enabled: bool = True


class CategoryOverride(BaseModel):
    """User override for a system highlight category."""

    name: str
    prompt: Optional[str] = None
    enabled: bool = True


class User(Document):
    """Registered user (linked to Telegram account)."""

    telegram_id: Indexed(int, unique=True)  # type: ignore[valid-type]
    username: Optional[str] = None
    display_name: str
    custom_categories: list[CustomCategory] = Field(default_factory=list)
    category_overrides: list[CategoryOverride] = Field(default_factory=list)
    bake_style_prompt: Optional[str] = None
    language: Literal["en", "uk", "ru"] = "en"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
