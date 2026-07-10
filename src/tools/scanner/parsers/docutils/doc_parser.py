"""Style-A docutils-based RST parser — the orchestrator.

The parser is intentionally thin: it walks the docutils tree once,
delegates each concern to a focused helper module, and assembles the
result into a :class:`ParsedDocument`. Style classification happens
upstream in :mod:`tools.scanner.parsers.docutils.style`; this module is
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

from tools.scanner.interfaces import ParsedDocument, RstParser
from tools.shared.exceptions import ParseFailure
from tools.shared.ir import HttpMethod
from tools.shared.report import (
    NESTED_STRUCT,
    SECTION_EXAMPLE_REQUEST,
    SECTION_EXAMPLE_RESPONSE,
    Issue,
    IssueCode,
    SectionResult,
    SectionStatus,
)

from .example import extract_examples
from .nesting import RefKind, RefTarget, resolve_nested
from .patterns import URI_RE
from .section import SectionKind, classify_section_title, classify_table_title
from .table import DETAILS_MAX, TableExtraction, extract_parameter_table


# OTC docs use Sphinx-specific roles like ``:ref:`Label <anchor>``` that
# bare docutils doesn't know about. Without a registered handler docutils
# inserts an inline ``system_message`` node that pollutes ``cell.astext()``
# output (so the cell text becomes ``"label\n\n... ERROR ... Unknown role"``).
# Register a no-op role that just emits the visible label text — clean
# extraction with no AST noise.
def _passthrough_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    # Keep the visible label as the node text (prose unchanged) and attach
    # the ref target as an attribute so the table extractor can read it.
    # ``text`` is the full role body, e.g. "CreateFirewallOption <anchor>".
    match = re.search(r"<([^>]+)>\s*$", text)
    anchor = match.group(1).strip() if match else None
    label = re.sub(r"\s*<[^>]+>\s*$", "", text).strip()
    node = nodes.inline(label, label)  # .astext() == label, prose unchanged
    if anchor:
        node["ref_target"] = anchor  # parser reads this; prose ignores it
    return [node], []


_roles_registered = False


def _ensure_roles() -> None:
    """Register the passthrough roles once, idempotently."""
    global _roles_registered
    if _roles_registered:
        return
    for role_name in ("ref", "doc", "term"):
        roles.register_local_role(role_name, _passthrough_role)
    _roles_registered = True


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

    def __init__(self) -> None:
        _ensure_roles()

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
        """Best-effort: regex on the URI first, then the source file path.

        The captured version is lower-cased so ``V1.0`` and ``v1.0`` land
        in the same bucket.
        """
        match = _VERSION_RE.search(uri)
        if match:
            return match.group(1).lower()
        match = _VERSION_RE.search("/" + source_path)
        if match:
            return match.group(1).lower()
        return None

    # ------------------------------------------------------------------ #
    # Content sections
    # ------------------------------------------------------------------ #
    def _extract_sections(self, doctree: nodes.document) -> dict[str, SectionResult]:
        """Two-pass extraction over every section in the doc.

        Sections of interest (URI / Request / Response / Example*) are
        typically *not* direct children of the doctree — they sit inside
        the article-title wrapper section — so we walk all sections at any
        depth and select by classification.

        A struct definition table can appear *after* the parameter that
        references it (and structs reference other structs defined later), so
        resolution needs the whole document first. Pass 1 routes primary
        tables into ``primary`` and collects struct tables into a doc-wide
        ``registry`` keyed by ref anchor; examples are handled inline. Pass 2
        resolves each section's object/array params against the registry,
        attaching any unresolved-ref issues to the owning section.
        """
        results: dict[str, SectionResult] = {}
        primary: dict[str, TableExtraction] = {}
        registry: dict[str, RefTarget] = {}

        # Pass 1 — primary tables, the struct registry, and examples.
        for section_node in doctree.findall(nodes.section):
            title_node = section_node.next_node(nodes.title)
            if title_node is None:
                continue
            kind = classify_section_title(title_node.astext())

            if kind in (SectionKind.URI, SectionKind.REQUEST, SectionKind.RESPONSE):
                self._collect_parameter_tables(section_node, kind, primary, registry)
            elif kind in (
                SectionKind.EXAMPLE_REQUEST,
                SectionKind.EXAMPLE_RESPONSE,
                SectionKind.EXAMPLE_COMBINED,
            ):
                self._extract_example_section(section_node, kind, results)
            # Other section kinds (article title, Function, Status Codes, …)
            # carry no data we currently extract — silently ignored.

        # A ref anchor pointing at a non-table node resolves to
        # NESTED_REF_NOT_A_TABLE rather than looking absent. Record these
        # after the struct tables so a real struct table keeps its anchor.
        _register_non_table_targets(doctree, registry)

        # This document's own label, so an unresolved anchor with a foreign
        # docid is reported as external rather than dangling.
        doc_id = _document_doc_id(doctree)

        # Pass 2 — resolve refs into children; attach failures to their owning
        # section and degrade OK → PARTIAL (worse statuses are left as-is).
        # Resolve one section at a time: the flat issue list carries no section
        # tag, so per-section calls are how we know which section each failure
        # belongs to. Resolution is otherwise identical to one combined call.
        for key, extraction in primary.items():
            issues = resolve_nested({key: extraction}, registry, doc_id=doc_id)
            section = _to_section_result(extraction)
            for issue in issues:
                section.issues.append(issue)
                if section.status is SectionStatus.OK:
                    section.status = SectionStatus.PARTIAL
            results[key] = section

        return results

    # ---- parameter-bearing sections (URI / Request / Response) ------ #
    def _collect_parameter_tables(
        self,
        section_node: nodes.section,
        kind: SectionKind,
        primary: dict[str, TableExtraction],
        registry: dict[str, RefTarget],
    ) -> None:
        """Pass-1 collector: route each table to ``primary`` or ``registry``."""
        for table in section_node.findall(nodes.table):
            target_key = classify_table_title(_table_title(table), in_section=kind)
            if target_key is None:
                # Status-code / non-parameter table — nothing to record.
                continue
            if target_key == NESTED_STRUCT:
                anchor = _table_label_id(table)
                if anchor:
                    registry[anchor] = RefTarget(
                        kind=RefKind.TABLE, table=extract_parameter_table(table)
                    )
                continue
            _accumulate(primary, target_key, extract_parameter_table(table))

    # ---- example sections ------------------------------------------- #
    def _extract_example_section(
        self,
        section_node: nodes.section,
        kind: SectionKind,
        results: dict[str, SectionResult],
    ) -> None:
        blocks = extract_examples(section_node)

        if kind is SectionKind.EXAMPLE_REQUEST:
            _set_example_section(results, SECTION_EXAMPLE_REQUEST, blocks)
        elif kind is SectionKind.EXAMPLE_RESPONSE:
            _set_example_section(results, SECTION_EXAMPLE_RESPONSE, blocks)
        else:  # EXAMPLE_COMBINED — split by label
            req, resp = [], []
            guessed = False
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
                    guessed = True
            extra = (
                [
                    Issue(
                        code=IssueCode.EXAMPLE_UNLABELED,
                        location="combined example section",
                        details="request/response split guessed (no labels)",
                    )
                ]
                if guessed
                else None
            )
            if req:
                _set_example_section(
                    results, SECTION_EXAMPLE_REQUEST, req, extra_issues=extra
                )
            if resp:
                _set_example_section(results, SECTION_EXAMPLE_RESPONSE, resp)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _table_title(table: nodes.table) -> str:
    """Title text on a ``.. table:: <Title>`` directive (empty if absent)."""
    title_node = next(iter(table.findall(nodes.title)), None)
    return title_node.astext().strip() if title_node else ""


def _table_label_id(table: nodes.table) -> str | None:
    """Ref anchor of a struct table: the label from its ``.. _anchor:`` target.

    We read ``names`` (the authored label, underscore-preserving) rather than
    ``ids`` (which docutils normalises to hyphens) so it matches the raw
    anchors captured from ``:ref:`` type cells in :mod:`.table`.
    """
    names = table.get("names")
    return names[0] if names else None


def _document_doc_id(doctree: nodes.document) -> str | None:
    """The document's own label (e.g. ``cce_02_0245``), or ``None``.

    OTC docs carry a ``.. _<docid>:`` target before the title, which lands on
    the top section alongside the title-derived name. We return the top
    section name that is *not* the title's — the authored docid, in the same
    underscore-preserving form as the ref anchors it will be compared against.
    """
    top = next(iter(doctree.findall(nodes.section)), None)
    if top is None:
        return None
    title_node = top.next_node(nodes.title)
    title_name = nodes.fully_normalize_name(title_node.astext()) if title_node else None
    for name in top.get("names", ()):
        if name != title_name:
            return name
    return None


def _accumulate(
    primary: dict[str, TableExtraction], key: str, extraction: TableExtraction
) -> None:
    """Merge an extraction into ``primary[key]``.

    A request can carry both a header table and a body table; tables sharing a
    target key are concatenated. ``ref_anchors`` is extended in lockstep with
    ``parameters`` so the 1:1 alignment the resolver relies on is preserved.
    """
    existing = primary.get(key)
    if existing is None:
        primary[key] = extraction
        return
    existing.parameters.extend(extraction.parameters)
    existing.ref_anchors.extend(extraction.ref_anchors)
    existing.issues.extend(extraction.issues)
    existing.fields_total += extraction.fields_total
    existing.fields_recognized += extraction.fields_recognized
    existing.fields_unknown_type += extraction.fields_unknown_type
    existing.fields_failed += extraction.fields_failed


def _to_section_result(extraction: TableExtraction) -> SectionResult:
    """Build a SectionResult from a (resolved) primary extraction."""
    return SectionResult(
        status=_status_from_counters(extraction),
        issues=list(extraction.issues),
        parameters=list(extraction.parameters),
        fields_total=extraction.fields_total,
        fields_recognized=extraction.fields_recognized,
        fields_unknown_type=extraction.fields_unknown_type,
        fields_failed=extraction.fields_failed,
    )


def _register_non_table_targets(
    doctree: nodes.document, registry: dict[str, RefTarget]
) -> None:
    """Record every named non-table node as a ``NON_TABLE`` target.

    A type-cell ref pointing at a section or paragraph then resolves to
    ``NESTED_REF_NOT_A_TABLE`` instead of looking absent. ``setdefault`` keeps
    struct tables (registered first, in pass 1) winning their own anchor.
    """
    for node in doctree.findall(nodes.Element):
        if isinstance(node, nodes.table):
            continue  # struct tables are registered in pass 1; primary aren't refs
        for name in node.get("names", ()):
            registry.setdefault(name, RefTarget(kind=RefKind.NON_TABLE))


def _status_from_counters(counters) -> SectionStatus:
    """Map field-level counters to a SectionStatus.

    Works on anything carrying ``fields_total`` / ``fields_failed`` /
    ``fields_unknown_type`` — both :class:`TableExtraction` and
    :class:`SectionResult` qualify, so one rule covers create and merge.
    """
    if counters.fields_total == 0:
        # The table existed but yielded no rows — structurally broken.
        return SectionStatus.FAILED
    if counters.fields_failed or counters.fields_unknown_type:
        return SectionStatus.PARTIAL
    return SectionStatus.OK


def _example_json_issues(blocks) -> list[Issue]:
    """One EXAMPLE_INVALID_JSON issue per block that didn't parse as JSON."""
    return [
        Issue(
            code=IssueCode.EXAMPLE_INVALID_JSON,
            location=f"example {i}",
            details=(b.label or "")[:DETAILS_MAX] or None,
        )
        for i, b in enumerate(blocks, start=1)
        if b.parsed is None
    ]


def _set_example_section(
    results: dict[str, SectionResult],
    key: str,
    blocks,
    *,
    extra_issues: list[Issue] | None = None,
) -> None:
    """Create or extend an example_* section.

    Invalid-JSON issues are computed on *both* the create and the extend
    path. ``extra_issues`` (e.g. EXAMPLE_UNLABELED) are informational
    and do not degrade the section by themselves.
    """
    if not blocks:
        return

    json_issues = _example_json_issues(blocks)
    extra = extra_issues or []

    existing = results.get(key)
    if existing is not None:
        existing.examples.extend(blocks)
        existing.issues.extend(json_issues)
        existing.issues.extend(extra)
        if any(i.code is IssueCode.EXAMPLE_INVALID_JSON for i in existing.issues):
            existing.status = SectionStatus.PARTIAL
        return

    status = SectionStatus.PARTIAL if json_issues else SectionStatus.OK
    results[key] = SectionResult(
        status=status,
        issues=[*json_issues, *extra],
        examples=list(blocks),
    )
