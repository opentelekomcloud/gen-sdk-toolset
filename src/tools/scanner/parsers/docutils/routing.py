"""Route docutils nodes into canonical endpoint sections."""

from __future__ import annotations

from dataclasses import dataclass, field

from docutils import nodes

from tools.shared.ir import (
    HttpMethod,
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
from .diagnostics import ISSUE_DETAILS_MAX
from .example import process_example_section, process_inline_examples
from .nesting import resolve_nested
from .path import reconcile_path_parameters
from .references import ReferenceRegistry, document_id
from .section import (
    classify_section_title,
    classify_table_title,
    default_table_section,
)
from .status_code import StatusCodeExtraction, extract_status_code_table
from .table import ExtractionMetrics, TableExtraction, extract_parameter_table
from .types import SectionKind, TableTarget


@dataclass
class _SectionExtraction:
    http_method: HttpMethod
    sections: dict[SectionName, Section] = field(default_factory=dict)
    primary_tables: dict[SectionName, TableExtraction] = field(default_factory=dict)
    references: ReferenceRegistry = field(default_factory=ReferenceRegistry)
    routing_issues: dict[SectionName, list[Issue]] = field(default_factory=dict)
    #: Status-code rows gathered from wherever the document wrote them.
    status_codes: StatusCodeExtraction = field(default_factory=StatusCodeExtraction)
    #: Tables already read as status codes, by identity. A status-code heading
    #: nested inside Request or Response is reached twice - once by the walk
    #: over that section, which recurses, and once by the walk over the heading
    #: itself - and the rows would otherwise be counted both times.
    read_status_tables: set[int] = field(default_factory=set)
    #: Blocks seen inside a request/response section that nothing consumed.
    #: Kept apart from routing_issues because they must not turn a parameter
    #: section into a failure - they belong to the example that was not read.
    unread_blocks: dict[SectionName, list[Issue]] = field(default_factory=dict)


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
        )
        if path_issues:
            extraction.routing_issues.setdefault(SectionName.PATH_PARAMS, []).extend(
                path_issues
            )
        extraction.references.register_non_table_targets(doctree)
        self._resolve_parameter_sections(
            extraction,
            doc_id=document_id(doctree),
        )
        _record_status_codes(extraction)
        _apply_routing_issues(extraction.sections, extraction.routing_issues)
        sections = _complete_sections(extraction.sections)
        _attach_unread_blocks(extraction.sections, extraction.unread_blocks)
        return sections

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
                if kind is not SectionKind.URI:
                    leftover = process_inline_examples(
                        section_node, extraction.sections
                    )
                    _report_unread_blocks(leftover, kind, extraction.unread_blocks)
                if context is not None:
                    extraction.references.register_explicit_field_tables(
                        section_node,
                        kind,
                        extraction.primary_tables,
                    )
            elif kind is SectionKind.STATUS_CODES:
                self._collect_status_code_tables(section_node, extraction)
            elif kind in (
                SectionKind.EXAMPLE_REQUEST,
                SectionKind.EXAMPLE_RESPONSE,
                SectionKind.EXAMPLE_COMBINED,
            ):
                process_example_section(
                    section_node,
                    kind,
                    extraction.sections,
                )

    @staticmethod
    def _collect_status_code_tables(
        section_node: nodes.section,
        extraction: _SectionExtraction,
    ) -> None:
        """Read every table under a status-code heading.

        Titles are not consulted here. Under this heading a table is the status
        codes by construction, and the corpus writes it three ways - a titled
        grid, a titled simple table, and a bare one with no title at all. Asking
        `classify_table_title` would route the untitled one to `UNMAPPED` and
        report a document that is perfectly well written.
        """
        for table in section_node.findall(nodes.table):
            _SectionRouter._collect_status_code_table(table, extraction)

    @staticmethod
    def _collect_status_code_table(
        table: nodes.table,
        extraction: _SectionExtraction,
    ) -> None:
        if id(table) in extraction.read_status_tables:
            return
        extraction.read_status_tables.add(id(table))
        extraction.status_codes.extend(extract_status_code_table(table))

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
            _SectionRouter._resolve_single_section(
                name, extraction, used_tables, doc_id
            )
        extraction.references.report_unused_tables(
            used_tables,
            extraction.routing_issues,
        )

    @staticmethod
    def _resolve_single_section(
        name: SectionName,
        extraction: _SectionExtraction,
        used_tables: set[int],
        doc_id: str | None,
    ) -> None:
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

        unmatched = extraction.references.unmatched_tables.get(name)
        if unmatched and section.scan_result is not None:
            section.scan_result.unmatched_tables = {
                key: unmatched_table.parameters
                for key, unmatched_table in unmatched.items()
            }

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
        target = _classify_table_target(
            table,
            title=title,
            section_kind=section_kind,
        )
        target = _resolve_generic_request_target(target, extraction.http_method)

        if target is SectionName.STATUS_CODES:
            _SectionRouter._collect_status_code_table(table, extraction)
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


def _record_status_codes(extraction: _SectionExtraction) -> None:
    """Put the gathered status codes into their section.

    Only rows make a section. A heading with nothing readable under it - the
    pages that carry a cross-reference to a shared status-code page and no table
    - leaves no section here, so `_complete_sections` records it as `missing`:
    the document really does list no status codes of its own, and saying
    `failed` would blame us for what the page does not contain.

    Issues go through `routing_issues` like every other routing diagnostic, so
    a table we could not read still turns the section `failed` even when it
    yielded no rows.
    """
    gathered = extraction.status_codes
    if gathered.issues:
        extraction.routing_issues.setdefault(SectionName.STATUS_CODES, []).extend(
            gathered.issues
        )
    if not gathered.codes:
        return
    extraction.sections[SectionName.STATUS_CODES] = Section(
        name=SectionName.STATUS_CODES,
        status_codes=list(gathered.codes),
        scan_result=SectionScanResult(status=SectionStatus.OK),
    )


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


_EXAMPLE_OF_KIND = {
    SectionKind.REQUEST: SectionName.EXAMPLE_REQUEST,
    SectionKind.RESPONSE: SectionName.EXAMPLE_RESPONSE,
}


def _attach_unread_blocks(
    sections: dict[SectionName, Section],
    unread: dict[SectionName, list[Issue]],
) -> None:
    """Record unread blocks on the example section they belong to.

    A section the document never wrote is ``missing``. A section whose content
    we saw and could not read is **not** missing - it is ``failed``, and the
    ``unmapped_block`` issue says what was left unread. Keeping the two apart is
    the whole point: `missing` is a fact about the documentation, `failed` is a
    fact about us.

    No data is invented: the section still carries no examples, because we did
    not read any.
    """
    for name, issues in unread.items():
        section = sections.get(name)
        if section is None or section.scan_result is None:
            continue
        section.scan_result.issues.extend(issues)
        if section.scan_result.status is SectionStatus.MISSING:
            section.scan_result.status = SectionStatus.FAILED


def _report_unread_blocks(
    blocks: list[nodes.literal_block],
    kind: SectionKind,
    issues_by_section: dict[SectionName, list[Issue]],
) -> None:
    """Record the blocks in this section that nothing consumed.

    A block the document labels as an example is extracted (see
    :func:`process_inline_examples`); what stays here is content we saw and
    could not place. Saying so is the point: an unread block is otherwise
    indistinguishable from an absent one, and `missing` would then claim the
    document has no example when we simply never read it.

    The issue is deliberately about the scanner, not about the documentation.
    """
    owner = _EXAMPLE_OF_KIND[kind]
    for index, block in enumerate(blocks, start=1):
        issues_by_section.setdefault(owner, []).append(
            Issue(
                code=IssueCode.UNMAPPED_BLOCK,
                location=f"{kind.value} block {index}",
                details=_block_preview(block),
            )
        )


def _block_preview(block: nodes.literal_block) -> str:
    text = " ".join(block.astext().split())
    return text[:ISSUE_DETAILS_MAX]


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
            status=_status_from_metrics(extraction.metrics),
            issues=list(extraction.issues),
            fields_total=extraction.metrics.fields_total,
            fields_recognized=extraction.metrics.fields_recognized,
            fields_unknown_type=extraction.metrics.fields_unknown_type,
            fields_failed=extraction.metrics.fields_failed,
        ),
    )


def _status_from_metrics(metrics: ExtractionMetrics) -> SectionStatus:
    if metrics.fields_total == 0:
        return SectionStatus.FAILED
    if metrics.fields_failed or metrics.fields_unknown_type:
        return SectionStatus.PARTIAL
    return SectionStatus.OK
