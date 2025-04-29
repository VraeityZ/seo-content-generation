"""Service layer that wraps core logic for easy import and future refactor."""
from importlib import import_module

# Re-export public APIs from child modules for convenience
for _mod in ("services.content_service", "services.analysis_service"):
    import_module(_mod)

from services.content_service import (
    generate_meta_and_headings,
    generate_content_from_headings,
    markdown_to_html,
    call_claude_api,
)
from services.analysis_service import analyze_content

__all__ = [
    "generate_meta_and_headings",
    "generate_content_from_headings",
    "markdown_to_html",
    "call_claude_api",
    "analyze_content",
]
