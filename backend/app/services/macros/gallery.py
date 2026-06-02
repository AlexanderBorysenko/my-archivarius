from typing import Optional

from app.services.macros.base import MacroSpec, register

MAX_IMAGES = 30
MAX_CAPTION = 300


def _validate_gallery(payload: dict, ctx: dict) -> Optional[dict]:
    raw = payload.get("images")
    if not isinstance(raw, list):
        return None
    images: list[str] = []
    for code in raw:
        if isinstance(code, str) and ctx.get(code) == "photo" and code not in images:
            images.append(code)
        if len(images) >= MAX_IMAGES:
            break
    if not images:
        return None
    caption = str(payload.get("caption") or "").strip()[:MAX_CAPTION]
    return {"images": images, "caption": caption}


register(MacroSpec(name="gallery", validate=_validate_gallery))
