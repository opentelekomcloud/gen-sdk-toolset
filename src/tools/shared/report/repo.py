from __future__ import annotations

from pydantic import BaseModel, Field

from tools import __version__ as _SCANNER_VERSION
from tools.shared.report.document import DocumentScanResult
from tools.shared.repository import RepositoryInterruption


class RepoScanResult(BaseModel):
    """Aggregated scan result for one repository."""

    repo: str
    branch: str
    commit_hash: str | None = None
    has_api_ref: bool = False

    # Version of the scanner/parser that produced this result, so report
    # diffing can tell "docs changed" from "parser improved" (addition A).
    scanner_version: str = _SCANNER_VERSION

    documents: list[DocumentScanResult] = Field(default_factory=list)

    # Files under api-ref/source/ that were *not* endpoint docs (intro
    # pages, conceptual material). Recorded here rather than dropped
    # silently so the inventory is honest.
    non_endpoint_documents: list[str] = Field(default_factory=list)

    # Files dropped before fetch because their path matched a configured
    # excluded segment (e.g. out-of-date_apis).
    excluded_documents: list[str] = Field(default_factory=list)

    # Successfully-or-partially extracted docs grouped by API version.
    # Failed / unsupported docs are *not* included here — they remain in
    # `documents`.
    documents_by_version: dict[str, list[DocumentScanResult]] = Field(
        default_factory=dict
    )

    # Set when the repo's file tree came back truncated from GitHub: the
    # scan saw only part of the files, so the result is not authoritative.
    incomplete: bool = False
    incomplete_reason: str | None = None

    # Set when the repo itself couldn't be scanned (e.g. tree fetch failed).
    #todo: do we really need those 2 fields?
    error: str | None = None
    interruption: RepositoryInterruption | None = None
