"""Derived status vocabularies used by report analytics."""

from enum import Enum


class OverallStatus(str, Enum):
    """Document-level roll-up of gating and section results."""

    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
