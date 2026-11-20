"""Render documentation findings as a markdown report for a human reader."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import groupby

from .finding import DocFinding

_INTRO = (
    "Only documentation errors the scanner detects reliably are listed. "
    "Review your changes yourself as well."
)


def render_markdown(
    findings: Sequence[DocFinding],
    *,
    repo: str,
    commit: str | None,
    dirty: bool,
) -> str:
    """Return the report: a header, then one table per file.

    ``findings`` are expected in the order :func:`find_doc_errors` returns them.
    """
    lines = [f"# API reference scan: {repo}", ""]
    if commit:
        lines.append(f"Commit: `{commit}`")
    if dirty:
        lines.append(
            "The working copy has changes after this commit; they are included."
        )
    lines += ["", _INTRO, ""]

    if not findings:
        lines.append("No documentation errors found.")
        return "\n".join(lines) + "\n"

    files = len({f.path for f in findings})
    lines += [f"**{len(findings)} documentation error(s) in {files} file(s).**", ""]
    for path, group in groupby(findings, key=lambda f: f.path):
        lines += [
            f"## {path}",
            "",
            "| Line | Section | Where | Problem |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| {_cell(str(f.line) if f.line else None)} | {_cell(f.section)} "
            f"| {_cell(f.location)} | {_cell(f.message)} |"
            for f in group
        ]
        lines.append("")
    return "\n".join(lines)


def _cell(value: str | None) -> str:
    if not value:
        return "—"
    # GitHub-flavoured tables split on "|" even inside code spans.
    return value.replace("|", "\\|").replace("\n", " ")
