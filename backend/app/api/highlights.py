"""Highlights API — ideas, stories, moods, insights extracted from entries."""

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.models.highlight import Highlight
from app.models.user import User, CustomCategory, CategoryOverride
from app.api.dependencies import get_current_user_id, get_current_user
from app.core.i18n import t, DEFAULT_LANG

router = APIRouter(prefix="/api/highlights", tags=["Highlights"])


SYSTEM_CATEGORIES = [
    {
        "name": "idea",
        "description": "Creative thoughts, plans, intentions",
        "prompt": "creative thoughts, plans, intentions, business ideas",
        "icon": "💡",
        "is_system": True,
    },
    {
        "name": "story",
        "description": "Events, trips, meetings, notable moments",
        "prompt": "notable events, trips, meetings, stories worth remembering",
        "icon": "📖",
        "is_system": True,
    },
    {
        "name": "mood",
        "description": "Emotions, mood, reflection",
        "prompt": "emotional state, reflection, psychological observations",
        "icon": "🧠",
        "is_system": True,
    },
    {
        "name": "insight",
        "description": "Conclusions, realizations, 'aha' moments",
        "prompt": "conclusions, realizations, 'aha' moments, life lessons, shifts in worldview, new understanding of oneself or life",
        "icon": "⚡",
        "is_system": True,
    },
]


def _get_override(user: User, name: str) -> Optional[CategoryOverride]:
    for ov in (user.category_overrides or []):
        if ov.name == name:
            return ov
    return None


class CreateCategoryRequest(BaseModel):
    name: str
    description: str
    prompt: str = ""
    icon: Optional[str] = None


class UpdateCategoryRequest(BaseModel):
    description: Optional[str] = None
    prompt: Optional[str] = None
    icon: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("")
async def list_highlights(
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """List highlights with optional category filter."""
    uid = ObjectId(user_id)
    query = {"user_id": uid}
    if category:
        query["category"] = category

    total = await Highlight.find(query).count()
    highlights = (
        await Highlight.find(query)
        .sort("-created_at")
        .skip((page - 1) * per_page)
        .limit(per_page)
        .to_list()
    )

    items = []
    for h in highlights:
        item = h.model_dump(mode="json")
        if h.date_range:
            item["source_date"] = h.date_range.from_date.isoformat()
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/categories")
async def list_categories(user: User = Depends(get_current_user)):
    """List system + user-defined categories with overrides applied."""
    categories = []
    for sys_cat in SYSTEM_CATEGORIES:
        cat = dict(sys_cat)
        override = _get_override(user, cat["name"])
        if override:
            if override.prompt is not None:
                cat["prompt"] = override.prompt
            cat["enabled"] = override.enabled
        else:
            cat["enabled"] = True
        categories.append(cat)

    for custom in (user.custom_categories or []):
        categories.append({
            "name": custom.name,
            "description": custom.description,
            "prompt": custom.prompt or "",
            "icon": custom.icon or "🏷️",
            "is_system": False,
            "enabled": custom.enabled,
        })
    return categories


@router.post("/categories", status_code=201)
async def create_category(
    body: CreateCategoryRequest,
    user: User = Depends(get_current_user),
):
    """Create a custom highlight category."""
    existing_names = [c.name for c in (user.custom_categories or [])]
    system_names = [c["name"] for c in SYSTEM_CATEGORIES]
    if body.name in existing_names or body.name in system_names:
        raise HTTPException(status_code=400, detail=t("category_exists", user.language))

    new_cat = CustomCategory(
        name=body.name,
        description=body.description,
        prompt=body.prompt,
        icon=body.icon,
    )
    if not user.custom_categories:
        user.custom_categories = []
    user.custom_categories.append(new_cat)
    await user.save()

    return {
        "name": new_cat.name,
        "description": new_cat.description,
        "prompt": new_cat.prompt,
        "icon": new_cat.icon or "🏷️",
        "is_system": False,
        "enabled": True,
    }


@router.put("/categories/{category_name}")
async def update_category(
    category_name: str,
    body: UpdateCategoryRequest,
    user: User = Depends(get_current_user),
):
    """Update a category. For system categories, stores an override."""
    system_names = [c["name"] for c in SYSTEM_CATEGORIES]

    if category_name in system_names:
        if not user.category_overrides:
            user.category_overrides = []
        override = _get_override(user, category_name)
        if override:
            if body.prompt is not None:
                override.prompt = body.prompt
            if body.enabled is not None:
                override.enabled = body.enabled
        else:
            override = CategoryOverride(
                name=category_name,
                prompt=body.prompt,
                enabled=body.enabled if body.enabled is not None else True,
            )
            user.category_overrides.append(override)
        await user.save()

        sys_cat = next(c for c in SYSTEM_CATEGORIES if c["name"] == category_name)
        return {
            "name": category_name,
            "description": sys_cat["description"],
            "prompt": override.prompt if override.prompt is not None else sys_cat["prompt"],
            "icon": sys_cat["icon"],
            "is_system": True,
            "enabled": override.enabled,
        }

    custom = next((c for c in (user.custom_categories or []) if c.name == category_name), None)
    if not custom:
        raise HTTPException(status_code=404, detail=t("category_not_found", user.language))

    if body.description is not None:
        custom.description = body.description
    if body.prompt is not None:
        custom.prompt = body.prompt
    if body.icon is not None:
        custom.icon = body.icon
    if body.enabled is not None:
        custom.enabled = body.enabled
    await user.save()

    return {
        "name": custom.name,
        "description": custom.description,
        "prompt": custom.prompt,
        "icon": custom.icon or "🏷️",
        "is_system": False,
        "enabled": custom.enabled,
    }


@router.delete("/categories/{category_name}", status_code=204)
async def delete_category(
    category_name: str,
    user: User = Depends(get_current_user),
):
    """Delete a custom category. System categories cannot be deleted."""
    system_names = [c["name"] for c in SYSTEM_CATEGORIES]
    if category_name in system_names:
        raise HTTPException(status_code=400, detail=t("cannot_delete_system_category", user.language))

    custom = next((c for c in (user.custom_categories or []) if c.name == category_name), None)
    if not custom:
        raise HTTPException(status_code=404, detail=t("category_not_found", user.language))

    user.custom_categories = [c for c in user.custom_categories if c.name != category_name]
    await user.save()


@router.get("/{highlight_id}")
async def get_highlight(
    highlight_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a specific highlight."""
    highlight = await Highlight.get(highlight_id)
    if not highlight or str(highlight.user_id) != user_id:
        user = await User.get(user_id)
        lang = user.language if user else DEFAULT_LANG
        raise HTTPException(status_code=404, detail=t("highlight_not_found", lang))
    return highlight.model_dump(mode="json")


@router.delete("/{highlight_id}", status_code=204)
async def delete_highlight(
    highlight_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a specific highlight."""
    highlight = await Highlight.get(highlight_id)
    if not highlight or str(highlight.user_id) != user_id:
        user = await User.get(user_id)
        lang = user.language if user else DEFAULT_LANG
        raise HTTPException(status_code=404, detail=t("highlight_not_found", lang))
    await highlight.delete()
