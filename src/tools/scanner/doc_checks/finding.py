"""One documentation error found in a scan result."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DocCheck(StrEnum):
    """Identifier of the check that produced a finding."""

    INVALID_JSON = "invalid_json"
    TYPE_TABLE_NUMBER = "type_table_number"
    TYPE_REFERENCE_MARKER = "type_reference_marker"
    TYPE_PROSE = "type_prose"
    TYPE_NEAR_PRIMITIVE = "type_near_primitive"
    PATH_PARAM_SPELLING = "path_param_spelling"
    REF_WHOLE_PAGE = "ref_whole_page"
    EMPTY_CODE_BLOCK = "empty_code_block"


@dataclass(frozen=True)
class DocFinding:
    """A documentation error, located as precisely as the scan result allows.

    ``json_line`` / ``json_column`` are set only for :attr:`DocCheck.INVALID_JSON`
    and point inside the example, not inside the RST file.
    """

    check: DocCheck
    path: str
    section: str | None
    location: str | None
    message: str
    json_line: int | None = None
    json_column: int | None = None
