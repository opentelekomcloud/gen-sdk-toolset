"""Example code-block extraction from docutils nodes.

Examples in OTC docs appear as ``.. code-block::`` directives or bare
``::`` literal blocks. Their content ranges from valid JSON to HTTP
wire-format (``POST https://… <body>``) to cURL fragments to JSON with
embedded ``//`` comments.

We capture the raw text verbatim and *attempt* to parse it as JSON
(best-effort) — when JSON parsing fails the ``parsed`` field stays
``None`` and the raw text is still available for downstream consumers.

Handles two layouts:

* code-blocks directly under an Example section, and
* bulleted list items under a combined ``Example`` / ``Examples``
  section (the KMS convention), where each bullet labels a child code
  block (``- Example request`` / ``- Example response``).
"""

from __future__ import annotations

import json

from docutils import nodes

from tools.domain.report import ExampleBlock

from .patterns import HTTP_PREFIX_RE


def extract_examples(section: nodes.section) -> list[ExampleBlock]:
    """Return every code/literal block inside a section.

    Each :class:`ExampleBlock` has its `label` set when the block sits
    under a labelled bullet (``- Example request``), and ``None``
    otherwise.
    """
    blocks: list[ExampleBlock] = []
    visited: set[int] = set()

    # First pass: bulleted-list layout (each bullet labels its blocks).
    for item in section.findall(nodes.list_item):
        label = _extract_item_label(item)
        for code in item.findall(nodes.literal_block):
            if id(code) in visited:
                continue
            visited.add(id(code))
            blocks.append(_make_example(code, label=label))

    # Second pass: any literal blocks not already collected via a bullet.
    for code in section.findall(nodes.literal_block):
        if id(code) in visited:
            continue
        visited.add(id(code))
        blocks.append(_make_example(code, label=None))

    return blocks


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _extract_item_label(item: nodes.list_item) -> str | None:
    """First paragraph text of a list_item, if any."""
    p = next(iter(item.findall(nodes.paragraph)), None)
    if p is None:
        return None
    text = p.astext().strip()
    return text or None


def _make_example(block: nodes.literal_block, *, label: str | None) -> ExampleBlock:
    raw = block.astext()
    language = block.get("language") or None
    return ExampleBlock(
        raw=raw,
        language=language,
        parsed=_try_parse_json(raw),
        label=label,
    )


def _try_parse_json(raw: str) -> dict | list | None:
    """Best-effort JSON parse. Returns None on any failure."""
    candidate = HTTP_PREFIX_RE.sub("", raw, count=1).strip()
    if not candidate:
        return None
    try:
        result = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(result, (dict, list)):
        return result
    return None
