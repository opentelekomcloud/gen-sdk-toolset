"""Canonical section keys — the single source of truth for the string keys
used in :attr:`DocumentScanResult.sections`.

Parsers import these constants instead of hardcoding string literals, so a
typo can't silently misfile a section. ``SECTION_NAMES`` is
built from them and is the stable, documented shape of the sections dict.
"""

from __future__ import annotations

SECTION_PATH_PARAMS = "path_params"
SECTION_QUERY_PARAMS = "query_params"
SECTION_HEADERS = "headers"
SECTION_BODY = "body"
SECTION_RESPONSE = "response"
SECTION_EXAMPLE_REQUEST = "example_request"
SECTION_EXAMPLE_RESPONSE = "example_response"
SECTION_NESTED_OBJECTS = "nested_objects"

# Canonical section names. Used as keys in DocumentScanResult.sections so the
# JSON output has a stable shape regardless of which sections a given doc
# actually contains.
#
# `nested_objects` is populated as a SKIPPED placeholder until the
# ref-resolution work (#6) lands — see IssueCode.NESTED_TABLE_SKIPPED.
SECTION_NAMES: tuple[str, ...] = (
    SECTION_PATH_PARAMS,
    SECTION_QUERY_PARAMS,
    SECTION_HEADERS,
    SECTION_BODY,
    SECTION_RESPONSE,
    SECTION_EXAMPLE_REQUEST,
    SECTION_EXAMPLE_RESPONSE,
    SECTION_NESTED_OBJECTS,
)

NESTED_STRUCT = "nested_struct"

# Bucket key used in `documents_by_version` for documents whose api_version
# could not be determined. Downstream consumers rely on this exact string.
UNVERSIONED_KEY = "unversioned"
