"""Route docutils nodes into canonical endpoint sections."""

from __future__ import annotations

from dataclasses import dataclass, field

from docutils import nodes

from tools.shared.ir import (
    HttpMethod,
    Parameter,
    Section,
    SectionName,
)
from tools.shared.scan import (
    Issue,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)

from .context import RepositoryParseContext
from .example import (
    add_examples_to_section,
    extract_examples,
    split_combined_examples,
)
from .inference import infer_documented_example_nesting
from .nesting import resolve_nested
from .path import reconcile_path_parameters
from .references import ReferenceRegistry, document_id
from .section import (
    SectionKind,
    TableTarget,
    classify_section_title,
    classify_table_title,
    default_table_section,
)
from .table import TableExtraction, extract_parameter_table


@dataclass
class _SectionExtraction:
    http_method: HttpMethod
    sections: dict[SectionName, Section] = field(default_factory=dict)
    primary_tables: dict[SectionName, TableExtraction] = field(default_factory=dict)
    references: ReferenceRegistry = field(default_factory=ReferenceRegistry)
    routing_issues: dict[SectionName, list[Issue]] = field(default_factory=dict)
    wrapper_candidates: dict[str, Parameter] = field(default_factory=dict)


_GENERIC_REQUEST_TARGETS = {
    HttpMethod.GET: SectionName.QUERY_PARAMS,
    HttpMethod.HEAD: SectionName.QUERY_PARAMS,
    HttpMethod.POST: SectionName.BODY,
    HttpMethod.PUT: SectionName.BODY,
    HttpMethod.PATCH: SectionName.BODY,
}

_DIRECT_UNTITLED_TARGETS = {
    SectionKind.URI: SectionName.PATH_PARAMS,
    SectionKind.REQUEST: TableTarget.GENERIC_REQUEST,
    SectionKind.RESPONSE: SectionName.RESPONSE,
}

class _SectionRouter:
    def extract(
        self,
        doctree: nodes.document,
        http_method: HttpMethod,
        uri: str,
        *,
        context: RepositoryParseContext | None,
    ) -> list[Section]:
        """Collect document data first, then resolve cross-table references."""
        extraction = _SectionExtraction(http_method=http_method)
        if context is not None:
            extraction.references.add_repository_tables(context.tables)
        self._collect_section_data(doctree, extraction, context=context)
        path_issues = reconcile_path_parameters(
            uri,
            extraction.primary_tables,
            extraction.wrapper_candidates,
        )
        if path_issues:
            extraction.routing_issues.setdefault(
                SectionName.PATH_PARAMS, []
            ).extend(path_issues)
        infer_documented_example_nesting(
            extraction.primary_tables,
            extraction.wrapper_candidates,
            extraction.sections,
            extraction.references.label_tables,
            extraction.references.unmatched_tables,
        )
        extraction.references.register_non_table_targets(doctree)
        self._resolve_parameter_sections(
            extraction,
            doc_id=document_id(doctree),
        )
        _apply_routing_issues(extraction.sections, extraction.routing_issues)
        return _complete_sections(extraction.sections)

    def _collect_section_data(
        self,
        doctree: nodes.document,
        extraction: _SectionExtraction,
        *,
        context: RepositoryParseContext | None,
    ) -> None:
        for section_node in doctree.findall(nodes.section):
            title_node = section_node.next_node(nodes.title)
            if title_node is None:
                continue
            kind = classify_section_title(title_node.astext())

            if kind in (SectionKind.URI, SectionKind.REQUEST, SectionKind.RESPONSE):
                self._collect_parameter_tables(section_node, kind, extraction)
                if context is not None:
                    extraction.references.register_explicit_field_tables(
                        section_node,
                        kind,
                        extraction.primary_tables,
                    )
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
        used_tables: set[int] = set()
        section_names = dict.fromkeys(
            (*extraction.primary_tables, *extraction.references.label_tables)
        )
        for name in section_names:
            table = extraction.primary_tables.get(name)
            section = (
                _to_section(table, name)
                if table is not None
                else Section(
                    name=name,
                    scan_result=SectionScanResult(status=SectionStatus.FAILED),
                )
            )
            issues = resolve_nested(
                {name: table} if table is not None else {},
                extraction.references.targets,
                doc_id=doc_id,
                label_tables=extraction.references.label_tables.get(name),
                used_tables=used_tables,
            )
            _append_issues(section, issues)
            extraction.sections[name] = section
        extraction.references.report_unused_tables(
            used_tables,
            extraction.routing_issues,
        )

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
        target = _classify_table_target(
            table,
            title=title,
            section_kind=section_kind,
        )
        target = _resolve_generic_request_target(target, extraction.http_method)

        if target is TableTarget.INTENTIONALLY_IGNORED:
            return
        if target is TableTarget.NESTED_STRUCT:
            if extraction.references.register_nested_table(
                table,
                title=title,
                section_kind=section_kind,
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


def extract_sections(
    doctree: nodes.document,
    http_method: HttpMethod,
    uri: str,
    *,
    context: RepositoryParseContext | None,
) -> list[Section]:
    return _SectionRouter().extract(
        doctree,
        http_method,
        uri,
        context=context,
    )


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
    if title or section_kind not in (
        SectionKind.URI,
        SectionKind.REQUEST,
        SectionKind.RESPONSE,
    ):
        return title
    return _list_item_label(table)


def _classify_table_target(
    table: nodes.table,
    *,
    title: str,
    section_kind: SectionKind,
) -> SectionName | TableTarget:
    if not title and isinstance(table.parent, nodes.section):
        return _DIRECT_UNTITLED_TARGETS[section_kind]
    return classify_table_title(title, in_section=section_kind)


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


def _accumulate(
    primary_tables: dict[SectionName, TableExtraction],
    name: SectionName,
    extraction: TableExtraction,
) -> None:
    """Merge an extraction into ``primary_tables[name]``.

    A request can carry both a header table and a body table; tables sharing a
    target key are concatenated.
    """
    existing = primary_tables.get(name)
    if existing is None:
        primary_tables[name] = extraction
        return
    existing.extend(extraction)


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


def _status_from_counters(counters: TableExtraction) -> SectionStatus:
    if counters.fields_total == 0:
        return SectionStatus.FAILED
    if counters.fields_failed or counters.fields_unknown_type:
        return SectionStatus.PARTIAL
    return SectionStatus.OK
