"""The parser puts the RST line of a broken JSON example on its issue."""

from __future__ import annotations

import pytest

from tools.scanner.parsers.docutils.example import ExampleBlock, add_examples_to_section
from tools.shared.ir import Example, SectionName
from tools.shared.scan import IssueCode


def _issue_line(raw: str, start_line: int | None) -> int | None:
    sections: dict = {}
    example = Example(raw=raw, language="json", parsed=None)
    add_examples_to_section(
        sections, SectionName.EXAMPLE_RESPONSE, [ExampleBlock(example, start_line)]
    )
    (issue,) = sections[SectionName.EXAMPLE_RESPONSE].scan_result.issues
    assert issue.code is IssueCode.EXAMPLE_INVALID_JSON
    return issue.line


# --------------------------------------------------------------------------- #
# Line of the JSON error
# --------------------------------------------------------------------------- #
def test_trailing_comma_is_on_the_comma_line() -> None:
    assert _issue_line('{\n  "a": 1,\n}', start_line=100) == 101


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The parser stops at "b" on the next line; the comma belongs after 1.
        ('{\n  "a": 1\n  "b": 2\n}', 101),
        # Missing comma inside one line stays on that line.
        ('{\n  "a": 1 "b": 2\n}', 101),
        # Missing colon after a key.
        ('{\n  "a"\n  1\n}', 101),
    ],
)
def test_missing_delimiter_points_to_where_it_belongs(raw, expected) -> None:
    assert _issue_line(raw, start_line=100) == expected


# --------------------------------------------------------------------------- #
# Lines before the JSON
# --------------------------------------------------------------------------- #
def test_http_request_line_and_blank_lines_are_counted() -> None:
    raw = 'POST /v1/things\n\n{\n  "a": 1,\n}'

    assert _issue_line(raw, start_line=40) == 43


def test_unknown_block_start_leaves_the_line_empty() -> None:
    assert _issue_line('{"a": 1,}', start_line=None) is None
