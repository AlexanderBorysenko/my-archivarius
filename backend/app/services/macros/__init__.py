"""Content-macro foundation. Importing this package registers all macro specs."""

from app.services.macros import gallery, figure  # noqa: F401  (registers specs)
from app.services.macros.base import MACRO_REGISTRY, MacroSpec, register  # noqa: F401
from app.services.macros.process import process_macros  # noqa: F401
