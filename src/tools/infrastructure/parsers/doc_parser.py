"""Style-A docutils-based RST parser — the orchestrator.

The parser is intentionally thin: it walks the docutils tree once,
delegates each concern to a focused helper module, and assembles the
result into a :class:`ParsedDocument`. Style classification happens
upstream in :mod:`tools.infrastructure.parsers.style`; this module is
only ever called on docs already known to be Style-A.

Outputs:

* Gating data (method, URI, title, api_version).
* A ``sections`` dict keyed by canonical section names, where each
  value is a :class:`SectionResult` with extracted parameters /
  examples plus field-level metrics.

A failure to extract the URI from the URI section raises
:class:`ParseFailure` so the scanner can record it as a gating failure.
"""

from __future__ import annotations

import io
import re

from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import roles

from tools.domain.interfaces.parser import RstParser
from tools.domain.ir import HttpMethod
from tools.domain.ir.enums import URI_RE
from tools.domain.report import (
    Issue,
    IssueCode,
    ParsedDocument,
    ParseFailure,
    SectionResult,
    SectionStatus,
)

from .example import extract_examples
from .section import SectionKind, classify_section_title, classify_table_title
from .table import extract_parameter_table


# OTC docs use Sphinx-specific roles like ``:ref:`Label <anchor>``` that
# bare docutils doesn't know about. Without a registered handler docutils
# inserts an inline ``system_message`` node that pollutes ``cell.astext()``
# output (so the cell text becomes ``"label\n\n... ERROR ... Unknown role"``).
# Register a no-op role that just emits the visible label text — clean
# extraction with no AST noise.
def _passthrough_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    label = re.sub(r"\s*<[^>]+>\s*$", "", text).strip()
    return [nodes.Text(label)], []


for _role_name in ("ref", "doc", "term"):
    roles.register_local_role(_role_name, _passthrough_role)

# Match "vN" or "vN.M" segments anywhere in a URI or file path. Used to
# infer api_version when the doc itself doesn't declare one.
_VERSION_RE = re.compile(r"/(v\d+(?:\.\d+)?)(?:/|$)", re.IGNORECASE)


class DocutilsParser(RstParser):
    # docutils complains about Sphinx-specific roles (:ref:, :doc:, etc.)
    # that aren't registered standalone. We don't care about those for
    # extraction — capture them in a throwaway stream so they don't leak
    # to the calling process's stderr.
    _SILENT_DOCUTILS_SETTINGS = {
        "report_level": 5,  # suppress everything but SEVERE
        "warning_stream": io.StringIO(),
    }

    def parse(self, content: str, path: str) -> ParsedDocument:
        doctree = publish_doctree(
            content, settings_overrides=self._SILENT_DOCUTILS_SETTINGS
        )

        method, uri = self._extract_method_and_uri(content, path)
        title = self._extract_title(doctree)
        api_version = self._extract_api_version(uri, path)
        sections = self._extract_sections(doctree)

        return ParsedDocument(
            method=method,
            uri=uri,
            title=title or None,
            api_version=api_version,
            sections=sections,
        )

    # ------------------------------------------------------------------ #
    # Gating
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_method_and_uri(content: str, path: str) -> tuple[HttpMethod, str]:
        match = URI_RE.search(content)
        if not match:
            raise ParseFailure(
                IssueCode.NO_URI_MATCH,
                details=f"No 'METHOD /path' line found in {path}",
            )
        return HttpMethod(match.group(1).upper()), match.group(2)

    @staticmethod
    def _extract_title(doctree: nodes.document) -> str:
        for section in doctree.findall(nodes.section):
            title_node = section.next_node(nodes.title)
            if title_node:
                return title_node.astext()
        return ""

    @staticmethod
    def _extract_api_version(uri: str, source_path: str) -> str | None:
        """Best-effort: regex on the URI first, then the source file path."""
        match = _VERSION_RE.search(uri)
        if match:
            return match.group(1)
        match = _VERSION_RE.search("/" + source_path)
        if match:
            return match.group(1)
        return None

    # ------------------------------------------------------------------ #
    # Content sections
    # ------------------------------------------------------------------ #
    def _extract_sections(self, doctree: nodes.document) -> dict[str, SectionResult]:
        """Walk every section in the doc, dispatch each by classified kind.

        Sections of interest (URI / Request / Response / Example*) are
        typically *not* direct children of the doctree — they sit inside
        the article-title wrapper section. We therefore walk all
        sections at any depth and select by classification.
        """
        results: dict[str, SectionResult] = {}

        for section_node in doctree.findall(nodes.section):
            title_node = section_node.next_node(nodes.title)
            if title_node is None:
                continue
            title = title_node.astext()
            kind = classify_section_title(title)

            if kind in (SectionKind.URI, SectionKind.REQUEST, SectionKind.RESPONSE):
                self._extract_parameter_section(section_node, kind, results)
            elif kind in (
                SectionKind.EXAMPLE_REQUEST,
                SectionKind.EXAMPLE_RESPONSE,
                SectionKind.EXAMPLE_COMBINED,
            ):
                self._extract_example_section(section_node, kind, results)
            # Other section kinds (article title, Function, Status Codes,
            # nested struct sub-sections, …) carry no data we currently
            # extract — silently ignored.

        return results

    # ---- parameter-bearing sections (URI / Request / Response) ------ #
    def _extract_parameter_section(
        self,
        section_node: nodes.section,
        kind: SectionKind,
        results: dict[str, SectionResult],
    ) -> None:
        for table in section_node.findall(nodes.table):
            table_title = _table_title(table)
            target_key = classify_table_title(table_title, in_section=kind)
            if target_key is None or target_key == "nested_struct":
                # Status-code tables or nested-struct tables — out of scope
                # for this PR (#6 will handle nested structs).
                continue
            self._merge_table_into_section(table, target_key, results)

    def _merge_table_into_section(
        self,
        table: nodes.table,
        key: str,
        results: dict[str, SectionResult],
    ) -> None:
        """Parse one table and merge its output into results[key]."""
        extraction = extract_parameter_table(table)

        existing = results.get(key)
        if existing is None:
            results[key] = SectionResult(
                status=_status_from_metrics(extraction),
                issues=list(extraction.issues),
                parameters=list(extraction.parameters),
                fields_total=extraction.fields_total,
                fields_recognized=extraction.fields_recognized,
                fields_unknown_type=extraction.fields_unknown_type,
                fields_failed=extraction.fields_failed,
            )
            return

        # Merge into the existing section (e.g. a request has both a
        # header table and a body table — same conceptual section keyed
        # together when their target keys match).
        existing.parameters.extend(extraction.parameters)
        existing.issues.extend(extraction.issues)
        existing.fields_total += extraction.fields_total
        existing.fields_recognized += extraction.fields_recognized
        existing.fields_unknown_type += extraction.fields_unknown_type
        existing.fields_failed += extraction.fields_failed
        existing.status = _status_from_section(existing)

    # ---- example sections ------------------------------------------- #
    def _extract_example_section(
        self,
        section_node: nodes.section,
        kind: SectionKind,
        results: dict[str, SectionResult],
    ) -> None:
        blocks = extract_examples(section_node)

        if kind is SectionKind.EXAMPLE_REQUEST:
            _set_example_section(results, "example_request", blocks)
        elif kind is SectionKind.EXAMPLE_RESPONSE:
            _set_example_section(results, "example_response", blocks)
        else:  # EXAMPLE_COMBINED — split by label
            req, resp = [], []
            for b in blocks:
                tag = (b.label or "").lower()
                if "response" in tag:
                    resp.append(b)
                elif "request" in tag:
                    req.append(b)
                else:
                    # No discriminating label — drop both into request as
                    # a fallback (most combined sections start with one).
                    req.append(b)
            if req:
                _set_example_section(results, "example_request", req)
            if resp:
                _set_example_section(results, "example_response", resp)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _table_title(table: nodes.table) -> str:
    """Title text on a ``.. table:: <Title>`` directive (empty if absent)."""
    title_node = next(iter(table.findall(nodes.title)), None)
    return title_node.astext().strip() if title_node else ""


def _status_from_metrics(extraction) -> SectionStatus:
    """Map TableExtraction metrics to a SectionStatus."""
    if extraction.fields_total == 0:
        # The table existed but yielded no rows — structurally broken.
        return SectionStatus.FAILED
    if extraction.fields_failed or extraction.fields_unknown_type:
        return SectionStatus.PARTIAL
    return SectionStatus.OK


def _status_from_section(section: SectionResult) -> SectionStatus:
    """Recompute status after merging additional rows into a SectionResult."""
    if section.fields_total == 0:
        return SectionStatus.FAILED
    if section.fields_failed or section.fields_unknown_type:
        return SectionStatus.PARTIAL
    return SectionStatus.OK


def _set_example_section(
    results: dict[str, SectionResult],
    key: str,
    blocks,
) -> None:
    """Create or extend an example_* section."""
    if not blocks:
        return
    if key in results:
        results[key].examples.extend(blocks)
        return

    # Note any JSON-parse failures as warnings (not section failures).
    issues = [
        Issue(
            code=IssueCode.EXAMPLE_INVALID_JSON,
            location=f"example {i}",
            details=(b.label or "")[:80] or None,
        )
        for i, b in enumerate(blocks, start=1)
        if b.parsed is None
    ]
    status = SectionStatus.PARTIAL if issues else SectionStatus.OK
    results[key] = SectionResult(status=status, issues=issues, examples=list(blocks))
