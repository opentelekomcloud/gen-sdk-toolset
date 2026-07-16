"""Canonical names assigned to extracted endpoint sections."""

from __future__ import annotations

SECTION_PATH_PARAMS = "path_params"
SECTION_QUERY_PARAMS = "query_params"
SECTION_HEADERS = "headers"
SECTION_BODY = "body"
SECTION_RESPONSE = "response"
SECTION_EXAMPLE_REQUEST = "example_request"
SECTION_EXAMPLE_RESPONSE = "example_response"

SECTION_NAMES: tuple[str, ...] = (
    SECTION_PATH_PARAMS,
    SECTION_QUERY_PARAMS,
    SECTION_HEADERS,
    SECTION_BODY,
    SECTION_RESPONSE,
    SECTION_EXAMPLE_REQUEST,
    SECTION_EXAMPLE_RESPONSE,
)

NESTED_STRUCT = "nested_struct"
UNVERSIONED_KEY = "unversioned"
