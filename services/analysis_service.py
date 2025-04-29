"""Facade for analysis functions to allow future expansion (e.g., linting)."""

from analysis import analyze_content  # noqa: F401 re-export

__all__ = ["analyze_content"]
