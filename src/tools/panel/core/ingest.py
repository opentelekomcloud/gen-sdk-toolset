"""Ingest a completed repository scan result into a persisted Generation.

The implementation lands in the ingest task (F2/F11). This module defines the
stable call site the background scan runner hands its completed
:class:`RepositoryScanResult` to.
"""

from __future__ import annotations

from tools.shared.scan import RepositoryScanResult


def ingest_service_result(
    *, job_id: int, service_repo: str, result: RepositoryScanResult
) -> None:
    """Persist a completed scan result as a Generation (next task)."""
    raise NotImplementedError("Implemented in the ingest task (F2/F11).")
