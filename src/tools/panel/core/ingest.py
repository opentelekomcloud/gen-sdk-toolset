"""Ingest a completed repository scan result into a persisted Generation.

Implemented in the next task; this module defines the stable call site the
scan runner hands its completed result to.
"""

from __future__ import annotations

from tools.shared.scan import RepositoryScanResult


def ingest_service_result(
    *, job_id: int, service_repo: str, result: RepositoryScanResult
) -> None:
    """Persist a completed scan result as a Generation (next task)."""
    raise NotImplementedError("ingest_service_result is implemented in the next task")
