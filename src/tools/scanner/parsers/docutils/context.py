"""Docutils setup and repository-wide parse context."""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import roles

from .table import TableExtraction, extract_parameter_table

logger = logging.getLogger(__name__)

_SILENT_DOCUTILS_SETTINGS = {
    "report_level": 5,
    "warning_stream": io.StringIO(),
}


@dataclass(frozen=True)
class RepositoryParseContext:
    """Parsed documents and parameter tables shared within one repository."""

    tables: Mapping[str, TableExtraction]
    doctrees: Mapping[str, nodes.document]


def _passthrough_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    """Preserve Sphinx role text and expose its target to the table parser."""
    match = re.search(r"<([^>]+)>\s*$", text)
    anchor = match.group(1).strip() if match else None
    label = re.sub(r"\s*<[^>]+>\s*$", "", text).strip()
    node = nodes.inline(label, label)
    if anchor:
        node["ref_target"] = anchor
    return [node], []


_roles_registered = False


def ensure_roles() -> None:
    global _roles_registered
    if _roles_registered:
        return
    for role_name in ("ref", "doc", "term"):
        roles.register_local_role(role_name, _passthrough_role)
    _roles_registered = True


def parse_doctree(content: str) -> nodes.document:
    ensure_roles()
    return publish_doctree(content, settings_overrides=_SILENT_DOCUTILS_SETTINGS)


def build_repository_context(
    documents: Mapping[str, str],
) -> RepositoryParseContext:
    tables: dict[str, TableExtraction] = {}
    doctrees: dict[str, nodes.document] = {}
    for path, content in documents.items():
        doctree = parse_doctree(content)
        doctrees[path] = doctree
        for table in doctree.findall(nodes.table):
            names = table.get("names")
            if not names:
                continue
            extracted = extract_parameter_table(table)
            if extracted.parameters:
                anchor = names[0]
                if anchor in tables:
                    # Repo-global anchors are expected to be unique (Sphinx
                    # cross-refs rely on it); a collision means a duplicate
                    # label authored across docs. Keep the first, but surface it.
                    logger.warning(
                        "Duplicate table anchor %r in %s; keeping first, "
                        "ignoring the later table",
                        anchor,
                        path,
                    )
                    continue
                tables[anchor] = extracted
    return RepositoryParseContext(tables=tables, doctrees=doctrees)
