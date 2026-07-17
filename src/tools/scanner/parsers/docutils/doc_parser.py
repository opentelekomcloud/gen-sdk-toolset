"""Parse Style-A RST documents into canonical endpoints."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import roles

from tools.scanner.interfaces import RstParser
from tools.shared.exceptions import ParseFailure
from tools.shared.ir import Endpoint, HttpMethod, Section, SectionName
from tools.shared.scan import (
    DocumentScanResult,
    Issue,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)

from .example import add_examples_to_section, extract_examples, split_combined_examples
from .nesting import RefKind, RefTarget, resolve_nested
from .patterns import URI_RE
from .section import (
    SectionKind,
    TableTarget,
    classify_section_title,
    classify_table_title,
    default_table_section,
)
from .style import extract_document_title
from .table import TableExtraction, extract_parameter_table


@dataclass
class _SectionExtraction:
    http_method: HttpMethod
    sections: dict[SectionName, Section] = field(default_factory=dict)
    primary_tables: dict[SectionName, TableExtraction] = field(default_factory=dict)
    reference_targets: dict[str, RefTarget] = field(default_factory=dict)
    routing_issues: dict[SectionName, list[Issue]] = field(default_factory=dict)


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


def _ensure_roles() -> None:
    global _roles_registered
    if _roles_registered:
        return
    for role_name in ("ref", "doc", "term"):
        roles.register_local_role(role_name, _passthrough_role)
    _roles_registered = True


_VERSION_RE = re.compile(r"/(v\d+(?:\.\d+)?)(?:/|$)", re.IGNORECASE)

_GENERIC_REQUEST_TARGETS = {
    HttpMethod.GET: SectionName.QUERY_PARAMS,
    HttpMethod.HEAD: SectionName.QUERY_PARAMS,
    HttpMethod.POST: SectionName.BODY,
    HttpMethod.PUT: SectionName.BODY,
    HttpMethod.PATCH: SectionName.BODY,
}


class DocutilsParser(RstParser):
    _SILENT_DOCUTILS_SETTINGS = {
        "report_level": 5,
        "warning_stream": io.StringIO(),
    }

    def __init__(self) -> None:
        _ensure_roles()

    def parse(self, content: str, path: str) -> Endpoint:
        doctree = publish_doctree(
            content, settings_overrides=self._SILENT_DOCUTILS_SETTINGS
        )

        method, uri = self._extract_method_and_uri(content, path)
        title = extract_document_title(content)
        api_version = self._extract_api_version(uri, path)
        sections = self._extract_sections(doctree, method)

        return Endpoint(
            path=path,
            title=title,
            method=method,
            uri=uri,
            api_version=api_version,
            sections=sections,
            scan_result=DocumentScanResult(),
        )

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
    def _extract_api_version(uri: str, source_path: str) -> str | None:
        """Read an API version from the URI, then fall back to the source path."""
        match = _VERSION_RE.search(uri)
        if match:
            return match.group(1).lower()
        match = _VERSION_RE.search("/" + source_path)
        if match:
            return match.group(1).lower()
        return None

    def _extract_sections(
        self,
        doctree: nodes.document,
        http_method: HttpMethod,
    ) -> list[Section]:
        """Collect document data first, then resolve cross-table references."""
        extraction = _SectionExtraction(http_method=http_method)
        self._collect_section_data(doctree, extraction)
        _register_non_table_targets(doctree, extraction.reference_targets)
        self._resolve_parameter_sections(
            extraction,
            doc_id=_document_doc_id(doctree),
        )
        _apply_routing_issues(extraction.sections, extraction.routing_issues)
        return _complete_sections(extraction.sections)

    def _collect_section_data(
        self,
        doctree: nodes.document,
        extraction: _SectionExtraction,
    ) -> None:
        for section_node in doctree.findall(nodes.section):
            title_node = section_node.next_node(nodes.title)
            if title_node is None:
                continue
            kind = classify_section_title(title_node.astext())

            if kind in (SectionKind.URI, SectionKind.REQUEST, SectionKind.RESPONSE):
                self._collect_parameter_tables(section_node, kind, extraction)
            elif kind in (
                SectionKind.EXAMPLE_REQUEST,
                SectionKind.EXAMPLE_RESPONSE,
                SectionKind.EXAMPLE_COMBINED,
            ):
                self._extract_example_section(
                    section_node,
                    kind,
                    extraction.sections,
                )

    @staticmethod
    def _resolve_parameter_sections(
        extraction: _SectionExtraction,
        *,
        doc_id: str | None,
    ) -> None:
        for name, table in extraction.primary_tables.items():
            section = _to_section(table, name)
            issues = resolve_nested(
                {name: table},
                extraction.reference_targets,
                doc_id=doc_id,
            )
            _append_issues(section, issues)
            extraction.sections[name] = section

    def _collect_parameter_tables(
        self,
        section_node: nodes.section,
        kind: SectionKind,
        extraction: _SectionExtraction,
    ) -> None:
        for table_index, table in enumerate(section_node.findall(nodes.table), start=1):
            self._route_parameter_table(
                table,
                index=table_index,
                section_kind=kind,
                extraction=extraction,
            )

    @staticmethod
    def _route_parameter_table(
        table: nodes.table,
        *,
        index: int,
        section_kind: SectionKind,
        extraction: _SectionExtraction,
    ) -> None:
        title = _table_routing_title(table, section_kind=section_kind)
        target = classify_table_title(title, in_section=section_kind)
        target = _resolve_generic_request_target(target, extraction.http_method)

        if target is TableTarget.INTENTIONALLY_IGNORED:
            return
        if target is TableTarget.NESTED_STRUCT and _register_reference_table(
            table, extraction.reference_targets
        ):
            return
        if isinstance(target, TableTarget):
            _add_unmapped_table_issue(
                extraction.routing_issues,
                section_kind=section_kind,
                table_index=index,
                title=title,
            )
            return

        _accumulate(
            extraction.primary_tables,
            target,
            extract_parameter_table(table),
        )

    def _extract_example_section(
        self,
        section_node: nodes.section,
        kind: SectionKind,
        sections: dict[SectionName, Section],
    ) -> None:
        blocks = extract_examples(section_node)

        if kind is SectionKind.EXAMPLE_REQUEST:
            add_examples_to_section(sections, SectionName.EXAMPLE_REQUEST, blocks)
            return
        if kind is SectionKind.EXAMPLE_RESPONSE:
            add_examples_to_section(sections, SectionName.EXAMPLE_RESPONSE, blocks)
            return

        request, response, issues = split_combined_examples(blocks)
        if request:
            add_examples_to_section(
                sections,
                SectionName.EXAMPLE_REQUEST,
                request,
                extra_issues=issues,
            )
        if response:
            add_examples_to_section(sections, SectionName.EXAMPLE_RESPONSE, response)


def _append_issues(section: Section, issues: list[Issue]) -> None:
    if not issues:
        return
    section.scan_result.issues.extend(issues)
    if section.scan_result.status is SectionStatus.OK:
        section.scan_result.status = SectionStatus.PARTIAL


def _apply_routing_issues(
    sections: dict[SectionName, Section],
    issues_by_section: dict[SectionName, list[Issue]],
) -> None:
    for name, issues in issues_by_section.items():
        section = sections.get(name)
        if section is None:
            sections[name] = Section(
                name=name,
                scan_result=SectionScanResult(
                    status=SectionStatus.FAILED,
                    issues=issues,
                ),
            )
            continue
        _append_issues(section, issues)


def _complete_sections(sections: dict[SectionName, Section]) -> list[Section]:
    for name in SectionName:
        sections.setdefault(
            name,
            Section(
                name=name,
                scan_result=SectionScanResult(status=SectionStatus.MISSING),
            ),
        )
    return [sections[name] for name in SectionName]


def _register_reference_table(
    table: nodes.table,
    targets: dict[str, RefTarget],
) -> bool:
    anchor = _table_label_id(table)
    if not anchor:
        return False
    targets[anchor] = RefTarget(
        kind=RefKind.TABLE,
        table=extract_parameter_table(table),
    )
    return True


def _add_unmapped_table_issue(
    issues_by_section: dict[SectionName, list[Issue]],
    *,
    section_kind: SectionKind,
    table_index: int,
    title: str,
) -> None:
    owner = default_table_section(section_kind)
    issues_by_section.setdefault(owner, []).append(
        Issue(
            code=IssueCode.UNMAPPED_TABLE,
            location=f"{section_kind.value} table {table_index}",
            details=title or "untitled table",
        )
    )


def _table_title(table: nodes.table) -> str:
    """Title text on a ``.. table:: <Title>`` directive (empty if absent)."""
    title_node = next(iter(table.findall(nodes.title)), None)
    return title_node.astext().strip() if title_node else ""


def _table_routing_title(table: nodes.table, *, section_kind: SectionKind) -> str:
    title = _table_title(table)
    if title or section_kind not in (SectionKind.URI, SectionKind.REQUEST):
        return title
    return _list_item_label(table)


def _resolve_generic_request_target(
    target: SectionName | TableTarget,
    http_method: HttpMethod,
) -> SectionName | TableTarget:
    if target is not TableTarget.GENERIC_REQUEST:
        return target
    return _GENERIC_REQUEST_TARGETS.get(http_method, TableTarget.UNMAPPED)


def _list_item_label(table: nodes.table) -> str:
    ancestor = table.parent
    while ancestor is not None and not isinstance(
        ancestor, (nodes.list_item, nodes.section)
    ):
        ancestor = ancestor.parent
    if not isinstance(ancestor, nodes.list_item):
        return ""
    paragraph = next(
        (child for child in ancestor.children if isinstance(child, nodes.paragraph)),
        None,
    )
    return paragraph.astext().strip() if paragraph else ""


def _table_label_id(table: nodes.table) -> str | None:
    """Ref anchor of a struct table: the label from its ``.. _anchor:`` target.

    We read ``names`` (the authored label, underscore-preserving) rather than
    ``ids`` (which docutils normalises to hyphens) so it matches the raw
    anchors captured from ``:ref:`` type cells in :mod:`.table`.
    """
    names = table.get("names")
    return names[0] if names else None


def _document_doc_id(doctree: nodes.document) -> str | None:
    """Return the authored document label rather than its title-derived name."""
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
    primary_tables: dict[SectionName, TableExtraction],
    name: SectionName,
    extraction: TableExtraction,
) -> None:
    """Merge an extraction into ``primary_tables[name]``.

    A request can carry both a header table and a body table; tables sharing a
    target key are concatenated. ``ref_anchors`` is extended in lockstep with
    ``parameters`` so the 1:1 alignment the resolver relies on is preserved.
    """
    existing = primary_tables.get(name)
    if existing is None:
        primary_tables[name] = extraction
        return
    existing.parameters.extend(extraction.parameters)
    existing.ref_anchors.extend(extraction.ref_anchors)
    existing.issues.extend(extraction.issues)
    existing.fields_total += extraction.fields_total
    existing.fields_recognized += extraction.fields_recognized
    existing.fields_unknown_type += extraction.fields_unknown_type
    existing.fields_failed += extraction.fields_failed


def _to_section(extraction: TableExtraction, name: SectionName) -> Section:
    return Section(
        name=name,
        parameters=list(extraction.parameters),
        scan_result=SectionScanResult(
            status=_status_from_counters(extraction),
            issues=list(extraction.issues),
            fields_total=extraction.fields_total,
            fields_recognized=extraction.fields_recognized,
            fields_unknown_type=extraction.fields_unknown_type,
            fields_failed=extraction.fields_failed,
        ),
    )


def _register_non_table_targets(
    doctree: nodes.document, targets: dict[str, RefTarget]
) -> None:
    """Record every named non-table node as a ``NON_TABLE`` target.

    A type-cell ref pointing at a section or paragraph then resolves to
    ``NESTED_REF_NOT_A_TABLE`` instead of looking absent. ``setdefault`` keeps
    struct tables (registered first, in pass 1) winning their own anchor.
    """
    for node in doctree.findall(nodes.Element):
        if isinstance(node, nodes.table):
            continue
        for name in node.get("names", ()):
            targets.setdefault(name, RefTarget(kind=RefKind.NON_TABLE))


def _status_from_counters(counters: TableExtraction) -> SectionStatus:
    if counters.fields_total == 0:
        return SectionStatus.FAILED
    if counters.fields_failed or counters.fields_unknown_type:
        return SectionStatus.PARTIAL
    return SectionStatus.OK
