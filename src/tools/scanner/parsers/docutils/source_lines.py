"""Find where a literal block starts in the RST source.

docutils does not record a block's first line reliably: ``node.line`` is the
first content line for a ``::`` literal block, the line *after* the block for
a ``code``/``code-block`` directive, and ``None`` for some blocks inside list
items. So the start is found by matching the block's text against the source
lines, and ``node.line`` only breaks a tie between identical blocks.
"""

from __future__ import annotations

from docutils import nodes

_SOURCE_LINES_ATTR = "_gen_sdk_source_lines"


def remember_source(doctree: nodes.document, content: str) -> None:
    """Keep the source lines on the doctree so blocks can be located later."""
    setattr(
        doctree, _SOURCE_LINES_ATTR, [line.strip() for line in content.splitlines()]
    )


def block_start_line(block: nodes.literal_block) -> int | None:
    """1-based source line of the block's first text line, or ``None``.

    ``None`` when the source is unknown, the text is not found verbatim, or
    identical blocks appear more than once and ``node.line`` does not say
    which one this is.
    """
    source = getattr(block.document, _SOURCE_LINES_ATTR, None)
    text = [line.strip() for line in block.astext().split("\n")]
    if not source or not text or not text[0]:
        return None
    size = len(text)
    starts = [
        index
        for index, line in enumerate(source[: len(source) - size + 1])
        if line == text[0] and source[index : index + size] == text
    ]
    if len(starts) == 1:
        return starts[0] + 1
    if block.line is not None:
        hinted = [s for s in starts if block.line in (s + 1, s + 1 + size)]
        if len(hinted) == 1:
            return hinted[0] + 1
    return None


def row_line(row: nodes.row) -> int | None:
    """1-based source line of a table row: the line of its first cell text.

    Rows and entries carry no line in docutils, but the paragraphs inside the
    cells do, for both simple and grid tables.
    """
    return next(
        (p.line for p in row.findall(nodes.paragraph) if p.line is not None),
        None,
    )
