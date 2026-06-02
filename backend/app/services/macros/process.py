import base64
import json
import re

from app.services.macros.base import MACRO_REGISTRY

MACRO_RE = re.compile(r"<!--\s*macro:([a-z][a-z0-9_]*)\s+(.+?)\s*-->", re.DOTALL)


def _decode_payload(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        return None


def _encode(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(data).decode("ascii")


def process_macros(content: str, ctx: dict) -> tuple[str, set]:
    """Validate + normalize every macro block. Returns (content, shortcodes_used)."""
    used: set[str] = set()

    def repl(m: re.Match) -> str:
        name, raw = m.group(1), m.group(2)
        spec = MACRO_REGISTRY.get(name)
        payload = _decode_payload(raw)
        if spec is None or payload is None:
            return ""
        norm = spec.validate(payload, ctx)
        if norm is None:
            return ""
        if "images" in norm:
            used.update(norm["images"])
        if "image" in norm:
            used.add(norm["image"])
        return f"<!-- macro:{name} {_encode(norm)} -->"

    return MACRO_RE.sub(repl, content), used
