"""Build the authored-reference registry consumed by nested-field resolution."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum

from docutils import nodes

from tools.shared.ir import SectionName
from tools.shared.scan import Issue, IssueCode

from .patterns import FIELD_DETAILS_RE
from .rst_nodes import first_authored_name, first_ref_target
from .section import default_table_section, nested_parent_name
from .table import TableExtraction, extract_parameter_table
from .types import SectionKind


class RefKind(str, Enum):
    """What an in-document ref anchor resolves to, classified by the wire-in.

    Repository context can contribute cross-document table entries. Missing
    cross-document refs are detected from the anchor's docid at lookup time.
    """

    TABLE = "table"  # a struct definition table in this document
    NON_TABLE = "non_table"  # anchor exists but points at a non-table node


@dataclass(frozen=True)
class RefTarget:
    """A resolved ref anchor. ``table`` is set only when ``kind is TABLE``."""

    kind: RefKind
    table: TableExtraction | None = None


@dataclass
class ReferenceRegistry:
    targets: dict[str, RefTarget] = field(default_factory=dict)
    table_sections: dict[str, SectionName] = field(default_factory=dict)
    label_tables: dict[SectionName, dict[str, TableExtraction]] = field(
        default_factory=dict
    )
    unmatched_tables: dict[SectionName, dict[str, TableExtraction]] = field(
        default_factory=dict
    )

    def add_repository_tables(self, tables: Mapping[str, TableExtraction]) -> None:
        self.targets.update(
            {
                anchor: RefTarget(kind=RefKind.TABLE, table=table)
                for anchor, table in tables.items()
            }
        )

    def register_nested_table(
        self,
        table: nodes.table,
        *,
        title: str,
        section_kind: SectionKind,
    ) -> bool:
        extracted = extract_parameter_table(table)
        by_reference = self._register_reference_table(
            table,
            extracted,
            section_kind=section_kind,
        )
        by_label = self._register_label_table(
            extracted,
            title=title,
            section_kind=section_kind,
        )
        return by_reference or by_label

    def register_explicit_field_tables(
        self,
        section_node: nodes.section,
        section_kind: SectionKind,
        primary_tables: Mapping[SectionName, TableExtraction],
    ) -> None:
        owner = default_table_section(section_kind)
        primary = primary_tables.get(owner)
        if primary is None:
            return
        parameter_names = {parameter.name for parameter in primary.parameters}

        for paragraph in section_node.findall(nodes.paragraph):
            self._process_field_details_paragraph(paragraph, parameter_names, owner)

    def _process_field_details_paragraph(
        self,
        paragraph: nodes.paragraph,
        parameter_names: set[str],
        owner: SectionName,
    ) -> None:
        match = FIELD_DETAILS_RE.search(paragraph.astext())
        if match is None:
            return
        parent_name = match.group(1)
        anchor = first_ref_target(paragraph)
        target = self.targets.get(anchor) if anchor else None
        if target is None or target.kind is not RefKind.TABLE or target.table is None:
            return

        referenced_table = deepcopy(target.table)
        if parent_name not in parameter_names:
            self.unmatched_tables.setdefault(owner, {}).setdefault(
                parent_name, referenced_table
            )
        else:
            self.label_tables.setdefault(owner, {}).setdefault(
                parent_name, referenced_table
            )

    def register_non_table_targets(self, doctree: nodes.document) -> None:
        for node in doctree.findall(nodes.Element):
            if isinstance(node, nodes.table):
                continue
            for name in node.get("names", ()):
                self.targets.setdefault(name, RefTarget(kind=RefKind.NON_TABLE))

    def report_unused_tables(
        self,
        used_tables: set[int],
        issues_by_section: dict[SectionName, list[Issue]],
    ) -> None:
        for anchor, section_name in self.table_sections.items():
            target = self.targets[anchor]
            if target.table is not None and id(target.table) in used_tables:
                continue
            issues_by_section.setdefault(section_name, []).append(
                Issue(
                    code=IssueCode.NESTED_PARENT_NOT_FOUND,
                    location=anchor,
                    details="nested table is not used by any parameter",
                )
            )

    def _register_reference_table(
        self,
        table: nodes.table,
        extracted: TableExtraction,
        *,
        section_kind: SectionKind,
    ) -> bool:
        anchor = first_authored_name(table)
        if not anchor:
            return False
        self.targets[anchor] = RefTarget(kind=RefKind.TABLE, table=extracted)
        self.table_sections[anchor] = default_table_section(section_kind)
        return True

    def _register_label_table(
        self,
        table: TableExtraction,
        *,
        title: str,
        section_kind: SectionKind,
    ) -> bool:
        parent_name = nested_parent_name(title)
        if parent_name is None:
            return False
        owner = default_table_section(section_kind)
        section_tables = self.label_tables.setdefault(owner, {})
        if parent_name in section_tables:
            return False
        section_tables[parent_name] = table
        return True


def document_id(doctree: nodes.document) -> str | None:
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
