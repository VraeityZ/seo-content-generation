"""Centralised logging helper.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
"""
from __future__ import annotations

import logging
import sys
from typing import Optional


_FMT = '%(asctime)s  %(levelname)-8s  %(name)s: %(message)s'


def _configure_root(level: int = logging.INFO) -> None:
    """Ensure the root logger has exactly one stream handler."""
    root = logging.getLogger()
    if root.handlers:
        return  # Already configured by first import
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT))
    root.addHandler(handler)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:  # noqa: D401
    """Return a module‑specific logger with root configured once."""
    _configure_root(level)
    return logging.getLogger(name)
