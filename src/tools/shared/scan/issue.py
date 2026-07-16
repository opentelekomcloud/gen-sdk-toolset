"""Structured issues emitted while scanning documents."""

from enum import Enum

from pydantic import BaseModel


class IssueCode(str, Enum):
    """Machine-readable codes for scanner diagnostics."""

    FETCH_FAILED = "fetch_failed"
    NOT_AN_ENDPOINT_DOC = "not_an_endpoint_doc"
    NO_URI_MATCH = "no_uri_match"
    PARSER_ERROR = "parser_error"
    UNSUPPORTED_DOC_STYLE = "unsupported_doc_style"

    TABLE_NOT_FOUND = "table_not_found"
    MALFORMED_GRID_TABLE = "malformed_grid_table"
    UNEXPECTED_COLUMNS = "unexpected_columns"

    UNKNOWN_TYPE_FORMAT = "unknown_type_format"
    EMPTY_MANDATORY_COLUMN = "empty_mandatory_column"
    DESCRIPTION_TRUNCATED = "description_truncated"

    NESTED_TABLE_NOT_FOUND = "nested_table_not_found"
    NESTED_TABLE_EMPTY = "nested_table_empty"
    NESTED_CIRCULAR_REF = "nested_circular_ref"
    NESTED_REF_NOT_A_TABLE = "nested_ref_not_a_table"
    NESTED_REF_EXTERNAL = "nested_ref_external"

    EXAMPLE_INVALID_JSON = "example_invalid_json"
    EXAMPLE_MISSING = "example_missing"
    EXAMPLE_UNLABELED = "example_unlabeled"
    EXAMPLE_LLM_FAILED = "example_llm_failed"


class Issue(BaseModel):
    """A single problem encountered while processing a document."""

    code: IssueCode
    location: str | None = None
    details: str | None = None
