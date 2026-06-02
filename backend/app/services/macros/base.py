from dataclasses import dataclass
from typing import Callable, Optional

# ctx is the user's media map: {shortcode: kind}
ValidateFn = Callable[[dict, dict], Optional[dict]]


@dataclass(frozen=True)
class MacroSpec:
    name: str
    validate: ValidateFn


MACRO_REGISTRY: dict[str, MacroSpec] = {}


def register(spec: MacroSpec) -> None:
    MACRO_REGISTRY[spec.name] = spec
