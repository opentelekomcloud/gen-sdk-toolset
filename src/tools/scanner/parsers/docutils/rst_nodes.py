"""Common operations for docutils AST nodes."""

from __future__ import annotations

from docutils import nodes


def all_ref_targets(node: nodes.Element) -> tuple[str, ...]:
    """Every inline ref_target anchor within a node, in order, without repeats.

    A cell may carry more than one - a description linking to both a structure
    table and a status-code page - and which of them means anything is a
    question for the caller, not for this traversal.
    """
    seen: dict[str, None] = {}
    for inline in node.findall(nodes.inline):
        target = inline.get("ref_target")
        if target:
            seen.setdefault(str(target), None)
    return tuple(seen)


def first_ref_target(node: nodes.Element) -> str | None:
    """Find the first inline ref_target anchor within a node."""
    return next(iter(all_ref_targets(node)), None)


def first_authored_name(node: nodes.Element) -> str | None:
    """Get the first explicitly authored name (label/anchor) of a node."""
    names = node.get("names", ())
    return str(names[0]) if names else None
