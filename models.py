"""Shared data models for the SEO Content Generator.

These dataclasses provide a single, typed representation of the SEO
requirements that flow between the parser, generator and analysis layers.
Using a schema avoids key‑name drift and enables IDE autocompletion while
remaining mostly backwards‑compatible with existing dict‐style access
(`obj.get('variations', [])`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Any


@dataclass
class HeadingTargets:
    """Desired counts for each heading level (H1‑H6)."""

    h1: int = 1
    h2: int = 0
    h3: int = 0
    h4: int = 0
    h5: int = 0
    h6: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HeadingTargets":
        return cls(
            h1=int(data.get("h1", data.get("Number of H1 tags", 1))),
            h2=int(data.get("h2", data.get("Number of H2 tags", 0))),
            h3=int(data.get("h3", data.get("Number of H3 tags", 0))),
            h4=int(data.get("h4", data.get("Number of H4 tags", 0))),
            h5=int(data.get("h5", data.get("Number of H5 tags", 0))),
            h6=int(data.get("h6", data.get("Number of H6 tags", 0))),
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            "h1": self.h1,
            "h2": self.h2,
            "h3": self.h3,
            "h4": self.h4,
            "h5": self.h5,
            "h6": self.h6,
        }


@dataclass
class SEORequirements:
    """Canonical container for all SEO requirement inputs."""

    primary_keyword: str
    variations: List[str] = field(default_factory=list)
    lsi_keywords: Dict[str, int] = field(default_factory=dict)
    entities: List[str] = field(default_factory=list)
    headings: HeadingTargets = field(default_factory=HeadingTargets)
    word_count: int = 1500
    images: int = 0
    basic_tunings: Dict[str, Any] = field(default_factory=dict)
    custom_entities: List[str] = field(default_factory=list)
    roadmap_requirements: Dict[str, Any] = field(default_factory=dict)
    debug_info: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Dict‑like helpers to ease incremental migration (existing code calls
    # requirements.get('variations', []), etc.)
    # ------------------------------------------------------------------

    def __getitem__(self, key: str):
        return self.__dict__[key]

    def get(self, key: str, default=None):
        return self.__dict__.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Return a deep copy as a plain dict (for JSON serialisation)."""
        data = asdict(self)
        data["headings"] = self.headings.to_dict()
        return data
