"""Controlled vocabularies for the scan quality report.

Every vocabulary here is a ``str``-Enum so JSON serialisation emits the
plain value (``"ok"``) and equality with bare strings still holds.
"""

from __future__ import annotations

from enum import Enum


class SectionStatus(str, Enum):
    """How well we extracted one section of a doc."""

    OK = "ok"  # fully extracted, no issues
    PARTIAL = "partial"  # extracted with one or more issues
    FAILED = "failed"  # section present in doc but extraction failed
    MISSING = "missing"  # section legitimately absent (e.g. GET with no body)
    SKIPPED = "skipped"  # parser doesn't handle this section in this doc


class OverallStatus(str, Enum):
    """Document-level roll-up of gating + per-section results.

    Distinct from :class:`SectionStatus`: this describes a *whole
    document*, that describes *one section*. The words overlap, the
    meanings don't — ``OverallStatus.OK`` means "gating passed and no
    section degraded", whereas a single ``SectionStatus.OK`` is the verdict
    on one section.

    * ``ok``          — gating passed, every section OK/MISSING.
    * ``partial``     — gating passed, ≥1 section partial / failed / skipped.
    * ``failed``      — a gating step failed (couldn't fetch / locate the URI).
    * ``unsupported`` — recognised but not yet extractable (e.g. S3-style docs).
    """

    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class IssueCode(str, Enum):
    """Structured codes for things that can go wrong during scanning."""

    # --- Gating (at most one per doc, in DocumentScanResult.failure_reason)
    FETCH_FAILED = "fetch_failed"
    NOT_AN_ENDPOINT_DOC = "not_an_endpoint_doc"
    NO_URI_MATCH = "no_uri_match"
    PARSER_ERROR = "parser_error"  # parser raised unexpectedly
    UNSUPPORTED_DOC_STYLE = "unsupported_doc_style"

    # --- Structural / table-level (in SectionResult.issues)
    TABLE_NOT_FOUND = "table_not_found"
    MALFORMED_GRID_TABLE = "malformed_grid_table"
    UNEXPECTED_COLUMNS = "unexpected_columns"

    # --- Field-level (in SectionResult.issues, with location="row N")
    UNKNOWN_TYPE_FORMAT = "unknown_type_format"
    EMPTY_MANDATORY_COLUMN = "empty_mandatory_column"
    DESCRIPTION_TRUNCATED = "description_truncated"

    # --- Nested resolution (#6)
    NESTED_TABLE_NOT_FOUND = "nested_table_not_found"  # ref anchor has no struct table
    NESTED_TABLE_EMPTY = "nested_table_empty"  # struct table found but has no fields
    NESTED_TABLE_SKIPPED = "nested_table_skipped"  # retired by #6 wire-in; unused
    NESTED_CIRCULAR_REF = "nested_circular_ref"  # struct references itself on the path
    NESTED_REF_NOT_A_TABLE = "nested_ref_not_a_table"  # anchor → non-table node
    NESTED_REF_EXTERNAL = "nested_ref_external"  # ref resolves into another doc

    # --- Examples
    EXAMPLE_INVALID_JSON = "example_invalid_json"
    EXAMPLE_MISSING = "example_missing"
    EXAMPLE_UNLABELED = "example_unlabeled"  # req/resp split guessed
    EXAMPLE_LLM_FAILED = "example_llm_failed"  # reserved for LLM-assisted parsing


class DocStyle(str, Enum):
    """Layout classification of an RST doc, mapped to report semantics.

    Mapping to report outcomes:

    * ``STYLE_A``       — modern OTC layout; handed to the parser. (A doc
      with endpoint headings but no extractable URI is still STYLE_A so the
      parser surfaces it as a ``no_uri_match`` gating failure)
    * ``S3_COMPATIBLE`` — OBS/S3 layout; recognised but not yet extractable →
      gating failure ``UNSUPPORTED_DOC_STYLE`` → ``overall_status``
      ``"unsupported"``.
    * ``NOT_ENDPOINT``  — no endpoint signal; excluded from quality metrics,
      recorded in ``RepoScanResult.non_endpoint_documents``.
    """

    STYLE_A = "style_a"
    S3_COMPATIBLE = "s3_compatible"
    NOT_ENDPOINT = "not_endpoint"
