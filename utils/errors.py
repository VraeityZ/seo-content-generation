"""Custom exception hierarchy and validation helpers."""
from __future__ import annotations


class SEOGeneratorError(RuntimeError):
    """Base class for all custom errors."""
    pass


class ParseError(SEOGeneratorError):
    """Raised when parsing of external data (e.g., CORA report) fails."""
    pass


class GenerationError(SEOGeneratorError):
    """Raised when AI content generation fails."""
    pass


class ValidationError(SEOGeneratorError):
    """Raised when user‑provided configuration is invalid."""
    pass


def expect(condition: bool, message: str, exc: type[SEOGeneratorError] = ValidationError):
    """Assert *condition* is truthy else raise *exc*(message)."""
    if not condition:
        raise exc(message)
