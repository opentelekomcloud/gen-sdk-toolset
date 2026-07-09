"""Org-level scan aggregate and the report analytics.

The report contracts (enums, keys, forms) live in
``tools.shared.report``. This package keeps what has not moved yet:
``OrgScanResult`` and the counting logic in :mod:`.analytics`.
"""

from __future__ import annotations

from .aggregates import REPORT_SCHEMA_VERSION, OrgScanResult
from .analytics import QualitySummary

__all__ = [
    "REPORT_SCHEMA_VERSION",
    "OrgScanResult",
    "QualitySummary",
]