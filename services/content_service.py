"""Wrapper around content_generator to decouple app from implementation."""
from __future__ import annotations

from typing import Any

# Re‑export selected functions to keep external contract stable
from content_generator import (
    call_claude_api,  # noqa: F401 re-export
    generate_meta_and_headings,  # noqa: F401 re-export
    generate_content_from_headings,  # noqa: F401 re-export
    markdown_to_html,  # noqa: F401 re-export
)

__all__: list[str] = [
    "call_claude_api",
    "generate_meta_and_headings",
    "generate_content_from_headings",
    "markdown_to_html",
]
