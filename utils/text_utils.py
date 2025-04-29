"""Utility helpers for high‑performance text processing.

The key feature is `multi_phrase_count` which counts occurrences of a
list of phrases in *O(N + M)* time using the Aho‑Corasick automaton when
`pyahocorasick` is available.  If the optional dependency is missing the
function gracefully falls back to a simple but slower `str.count`
implementation.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, List


@lru_cache(maxsize=128)
def _build_automaton(phrases: tuple[str, ...]):  # type: ignore[name-defined]
    """Build and cache an Aho‑Corasick automaton for the given phrases."""
    try:
        import ahocorasick  # type: ignore
    except ImportError:
        return None  # Will trigger fallback path

    A = ahocorasick.Automaton()
    for phrase in phrases:
        # Use lowercase tokenisation to make search case‑insensitive
        A.add_word(phrase, phrase)
    A.make_automaton()
    return A


def multi_phrase_count(text: str, phrases: Iterable[str]) -> Dict[str, int]:
    """Return occurrence counts for each phrase inside *text*.

    Parameters
    ----------
    text: str
        Body of text to search (should already be lower‑cased for
        case‑insensitive matching).
    phrases: Iterable[str]
        List, tuple or set of phrases.  Matching is done against the exact
        sequence of characters – implement your own stemming if required.
    """
    phrases_list: List[str] = [p.lower().strip() for p in phrases if p]
    if not phrases_list:
        return {}

    # Try high‑performance Aho‑Corasick implementation first
    automaton = _build_automaton(tuple(phrases_list))
    if automaton is not None:
        counts = {p: 0 for p in phrases_list}
        for _, found in automaton.iter(text.lower()):
            counts[found] += 1
        return counts

    # Fallback: naive counting using str.count (still O(N·M))
    counts = {}
    padded_text = f" {text.lower()} "
    for p in phrases_list:
        counts[p] = padded_text.count(f" {p} ")
    return counts
