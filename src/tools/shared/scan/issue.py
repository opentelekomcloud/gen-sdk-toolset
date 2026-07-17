"""Structured issues emitted while scanning documents."""

from enum import Enum

from pydantic import BaseModel


class IssueCode(str, Enum):
    """Machine-readable codes for scanner diagnostics."""

    FETCH_FAILED = "fetch_failed"
    NO_URI_MATCH = "no_uri_match"
    PARSER_ERROR = "parser_error"
    UNSUPPORTED_DOC_STYLE = "unsupported_doc_style"

    MALFORMED_GRID_TABLE = "malformed_grid_table"
    UNEXPECTED_COLUMNS = "unexpected_columns"
    UNMAPPED_TABLE = "unmapped_table"

    UNKNOWN_TYPE_FORMAT = "unknown_type_format"

    NESTED_TABLE_NOT_FOUND = "nested_table_not_found"
    NESTED_PARENT_NOT_FOUND = "nested_parent_not_found"
    NESTED_TABLE_EMPTY = "nested_table_empty"
    NESTED_CIRCULAR_REF = "nested_circular_ref"
    NESTED_REF_NOT_A_TABLE = "nested_ref_not_a_table"
    NESTED_REF_EXTERNAL = "nested_ref_external"

    EXAMPLE_INVALID_JSON = "example_invalid_json"
    EXAMPLE_UNLABELED = "example_unlabeled"


class Issue(BaseModel):
    """A single problem encountered while processing a document."""

    code: IssueCode
    location: str | None = None
    details: str | None = None
