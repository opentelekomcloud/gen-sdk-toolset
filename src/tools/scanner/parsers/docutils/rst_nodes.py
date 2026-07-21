"""Common operations for docutils AST nodes."""

from __future__ import annotations

from docutils import nodes


def first_ref_target(node: nodes.Element) -> str | None:
    """Find the first inline ref_target anchor within a node."""
    for inline in node.findall(nodes.inline):
        target = inline.get("ref_target")
        if target:
            return str(target)
    return None


def first_authored_name(node: nodes.Element) -> str | None:
    """Get the first explicitly authored name (label/anchor) of a node."""
    names = node.get("names", ())
    return str(names[0]) if names else None
