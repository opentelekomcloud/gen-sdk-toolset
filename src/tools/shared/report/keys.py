"""Canonical names assigned to extracted endpoint sections."""

from __future__ import annotations

from tools.shared.ir import SectionName

SECTION_PATH_PARAMS = SectionName.PATH_PARAMS
SECTION_QUERY_PARAMS = SectionName.QUERY_PARAMS
SECTION_HEADERS = SectionName.HEADERS
SECTION_BODY = SectionName.BODY
SECTION_RESPONSE = SectionName.RESPONSE
SECTION_EXAMPLE_REQUEST = SectionName.EXAMPLE_REQUEST
SECTION_EXAMPLE_RESPONSE = SectionName.EXAMPLE_RESPONSE

SECTION_NAMES: tuple[SectionName, ...] = tuple(SectionName)

NESTED_STRUCT = "nested_struct"
UNVERSIONED_KEY = "unversioned"
