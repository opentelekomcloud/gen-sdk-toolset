"""Locating a literal block's first line in the RST source."""

from __future__ import annotations

from docutils import nodes

from tools.scanner.parsers.docutils.context import parse_doctree
from tools.scanner.parsers.docutils.source_lines import block_start_line

SOURCE = """\
Title
=====

-  Example request

   .. code-block:: json

      {
          "a": 1
      }

Literal::

   {"b": 2}

.. code:: json

   {"c": 3}

-  item

   ::

      {"d": 4}
"""


def _lines(source: str) -> list[int | None]:
    doctree = parse_doctree(source)
    return [block_start_line(b) for b in doctree.findall(nodes.literal_block)]


# --------------------------------------------------------------------------- #
# Literal blocks
# --------------------------------------------------------------------------- #
def test_each_kind_of_block_starts_on_its_first_text_line() -> None:
    """Would catch trusting docutils' node.line: it points after a code-block,
    at a `::` block's first line, and is missing inside list items."""
    assert _lines(SOURCE) == [8, 14, 18, 24]


def test_identical_blocks_without_a_tie_breaker_have_no_line() -> None:
    source = (
        "Title\n=====\n\n"
        "-  Example request\n\n   .. code-block:: json\n\n      {}\n\n"
        "-  Example response\n\n   .. code-block:: json\n\n      {}\n"
    )

    assert _lines(source) == [None, None]


def test_identical_literal_blocks_are_told_apart_by_node_line() -> None:
    source = "Title\n=====\n\nOne::\n\n   {}\n\nTwo::\n\n   {}\n"

    assert _lines(source) == [6, 10]


def test_block_outside_a_parsed_source_has_no_line() -> None:
    assert block_start_line(nodes.literal_block("{}", "{}")) is None


# --------------------------------------------------------------------------- #
# Table rows
# --------------------------------------------------------------------------- #
def test_table_rows_point_to_their_own_line() -> None:
    from tools.scanner.parsers.docutils.source_lines import row_line

    source = (
        "Title\n=====\n\n"
        ".. table:: **Table 1** Parameters\n\n"
        "   ========= ========= ======\n"
        "   Parameter Mandatory Type\n"
        "   ========= ========= ======\n"
        "   a         Yes       String\n"
        "   b         No        Table 2\n"
        "   ========= ========= ======\n"
    )
    doctree = parse_doctree(source)

    assert [row_line(r) for r in doctree.findall(nodes.row)] == [7, 9, 10]
