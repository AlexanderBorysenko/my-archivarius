from typing import Optional

from app.services.macros.base import MacroSpec, register

WIDTHS = (25, 33, 50, 100)
ALIGNS = ("left", "right", "center", "full")
MAX_CAPTION = 300


def _snap_width(value) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 33
    return min(WIDTHS, key=lambda w: abs(w - v))


def _validate_figure(payload: dict, ctx: dict) -> Optional[dict]:
    code = payload.get("image")
    if not isinstance(code, str) or ctx.get(code) != "photo":
        return None
    width = _snap_width(payload.get("width", 33))
    align = payload.get("align") if payload.get("align") in ALIGNS else "left"
    if width == 100:
        align = "full"
    caption = str(payload.get("caption") or "").strip()[:MAX_CAPTION]
    return {"image": code, "width": width, "align": align, "caption": caption}


register(MacroSpec(name="figure", validate=_validate_figure))
