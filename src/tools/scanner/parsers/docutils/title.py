"""Extraction of the document title from raw RST text."""

from __future__ import annotations

_RST_TITLE_UNDERLINE_CHARS = frozenset("=-~^\"'`#*+")


def extract_document_title(content: str) -> str | None:
    """Return the first RST overline-free heading in a document."""
    lines = content.splitlines()
    for title_line, underline_line in zip(lines, lines[1:]):
        if (
            title_line != title_line.lstrip()
            or underline_line != underline_line.lstrip()
        ):
            continue
        title = title_line.rstrip()
        underline = underline_line.rstrip()
        if not title or len(underline) < 3:
            continue
        if len(underline) < len(title):
            continue
        if len(set(underline)) != 1:
            continue
        if underline[0] in _RST_TITLE_UNDERLINE_CHARS:
            return title
    return None
