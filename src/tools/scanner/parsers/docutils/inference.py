"""Infer nesting only when documentation and parsed examples agree."""

from __future__ import annotations

from collections.abc import Iterator

from tools.shared.ir import Parameter, ParameterType, Section, SectionName
from tools.shared.scan import IssueCode

from .table import TableExtraction, TableRow

_EXAMPLE_SECTIONS = {
    SectionName.BODY: SectionName.EXAMPLE_REQUEST,
    SectionName.RESPONSE: SectionName.EXAMPLE_RESPONSE,
}


def infer_documented_example_nesting(
    primary_tables: dict[SectionName, TableExtraction],
    wrapper_candidates: dict[str, Parameter],
    sections: dict[SectionName, Section],
    label_tables: dict[SectionName, dict[str, TableExtraction]],
    unmatched_reference_tables: dict[
        SectionName, dict[str, TableExtraction]
    ] | None = None,
) -> None:
    """Group documented fields when parsed examples prove their nesting."""
    for parameter_section, example_section in _EXAMPLE_SECTIONS.items():
        table = primary_tables.get(parameter_section)
        example_section_data = sections.get(example_section)
        if table is None or example_section_data is None:
            continue
        parsed_examples = _valid_parsed_examples(example_section_data)
        if not parsed_examples:
            continue
        section_labels = label_tables.setdefault(parameter_section, {})
        _infer_root_wrapper(
            table,
            parsed_examples,
            wrapper_candidates,
            (unmatched_reference_tables or {}).get(parameter_section, {}),
            section_labels,
        )
        _infer_arrays_in_documented_tables(
            table,
            parsed_examples,
            section_labels,
        )


def _infer_root_wrapper(
    table: TableExtraction,
    parsed_examples: list[dict | list],
    wrapper_candidates: dict[str, Parameter],
    reference_tables: dict[str, TableExtraction],
    label_tables: dict[str, TableExtraction],
) -> None:
    root = _consistent_example_root(parsed_examples)
    if root is None:
        return

    root_name, is_array, example_fields = root
    nested_table = _apply_top_level_wrapper(
        table,
        wrapper_candidates.get(root_name),
        root_name=root_name,
        is_array=is_array,
        example_fields=example_fields,
    )
    if nested_table is not None:
        label_tables.setdefault(root_name, nested_table)
    _bind_referenced_root(
        table,
        root_name=root_name,
        is_array=is_array,
        example_fields=example_fields,
        candidates=reference_tables,
        label_tables=label_tables,
    )


def _infer_arrays_in_documented_tables(
    primary_table: TableExtraction,
    parsed_examples: list[dict | list],
    label_tables: dict[str, TableExtraction],
) -> None:
    for table in [primary_table, *list(label_tables.values())]:
        _infer_nested_arrays(table, parsed_examples, label_tables)


def _bind_referenced_root(
    table: TableExtraction,
    *,
    root_name: str,
    is_array: bool,
    example_fields: set[str],
    candidates: dict[str, TableExtraction],
    label_tables: dict[str, TableExtraction],
) -> None:
    if root_name in label_tables:
        return
    wrapper = next(
        (parameter for parameter in table.parameters if parameter.name == root_name),
        None,
    )
    if wrapper is None or wrapper.children:
        return
    if is_array and wrapper.param_type not in {
        ParameterType.ARRAY,
        ParameterType.ARRAY_OF_OBJECTS,
    }:
        return
    if not is_array and wrapper.param_type is not ParameterType.OBJECT:
        return

    matches: dict[int, TableExtraction] = {}
    for candidate in candidates.values():
        documented = {parameter.name for parameter in candidate.parameters}
        if example_fields and example_fields.issubset(documented):
            matches.setdefault(id(candidate), candidate)
    if len(matches) != 1:
        return

    if wrapper.param_type is ParameterType.ARRAY:
        wrapper.param_type = ParameterType.ARRAY_OF_OBJECTS
    label_tables[root_name] = next(iter(matches.values()))


def _valid_parsed_examples(section: Section) -> list[dict | list]:
    if section.scan_result is not None and any(
        issue.code is IssueCode.EXAMPLE_INVALID_JSON
        for issue in section.scan_result.issues
    ):
        return []
    return [example.parsed for example in section.examples if example.parsed]


def _consistent_example_root(
    parsed_examples: list[dict | list],
) -> tuple[str, bool, set[str]] | None:
    roots = [_structured_root(example) for example in parsed_examples]
    if any(root is None for root in roots):
        return None
    resolved = [root for root in roots if root is not None]
    name, is_array, _ = resolved[0]
    if any(root_name != name or array != is_array for root_name, array, _ in resolved):
        return None
    fields = set().union(*(root_fields for _, _, root_fields in resolved))
    return name, is_array, fields


def _infer_nested_arrays(
    table: TableExtraction,
    parsed_examples: list[dict | list],
    label_tables: dict[str, TableExtraction],
) -> None:
    for parameter in list(table.parameters):
        if (
            parameter.param_type
            not in {ParameterType.ARRAY, ParameterType.ARRAY_OF_OBJECTS}
            or parameter.children
            or parameter.name in label_tables
        ):
            continue
        child_names = _documented_array_children(
            parameter.name,
            {item.name for item in table.parameters},
            parsed_examples,
        )
        if not child_names:
            continue
        nested_table = _move_named_children(table, parameter, child_names)
        if nested_table is None:
            continue
        parameter.param_type = ParameterType.ARRAY_OF_OBJECTS
        label_tables[parameter.name] = nested_table


def _documented_array_children(
    parent_name: str,
    documented_names: set[str],
    examples: list[dict | list],
) -> set[str] | None:
    matches: list[set[str]] = []
    sibling_names = documented_names - {parent_name}
    for example in examples:
        for container in _object_nodes(example):
            if parent_name not in container:
                continue
            if not sibling_names.intersection(container):
                continue
            value = container[parent_name]
            if not isinstance(value, list) or not value:
                return None
            if not all(isinstance(item, dict) for item in value):
                return None
            nested_names = set().union(*(set(item) for item in value))
            matches.append(nested_names & sibling_names)
    if not matches or any(not match for match in matches):
        return None
    return set().union(*matches)


def _object_nodes(value: dict | list) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                yield from _object_nodes(nested)
    else:
        for nested in value:
            if isinstance(nested, (dict, list)):
                yield from _object_nodes(nested)


def _move_named_children(
    table: TableExtraction,
    parent: Parameter,
    child_names: set[str],
) -> TableExtraction | None:
    child_rows = [
        row
        for row in table.rows
        if row.parameter is not parent and row.parameter.name in child_names
    ]
    if not child_rows:
        return None
    child_ids = {id(row.parameter) for row in child_rows}
    table.rows = [
        row for row in table.rows if id(row.parameter) not in child_ids
    ]
    return TableExtraction(
        rows=child_rows,
        issues=[],
        fields_total=len(child_rows),
        fields_recognized=len(child_rows),
        fields_unknown_type=0,
        fields_failed=0,
    )


def _structured_root(value: dict | list) -> tuple[str, bool, set[str]] | None:
    if not isinstance(value, dict) or len(value) != 1:
        return None
    name, nested = next(iter(value.items()))
    if isinstance(nested, dict):
        return name, False, set(nested)
    if not isinstance(nested, list) or not nested:
        return None
    if not all(isinstance(item, dict) for item in nested):
        return None
    return name, True, set().union(*(set(item) for item in nested))


def _apply_top_level_wrapper(
    table: TableExtraction,
    candidate: Parameter | None,
    *,
    root_name: str,
    is_array: bool,
    example_fields: set[str],
) -> TableExtraction | None:
    existing_index = next(
        (
            index
            for index, row in enumerate(table.rows)
            if row.parameter.name == root_name
        ),
        None,
    )
    wrapper = (
        table.rows[existing_index].parameter
        if existing_index is not None
        # Copy the candidate: it is owned by wrapper_candidates and must not be
        # mutated in place (its param_type is repurposed below).
        else candidate.model_copy(deep=True)
        if candidate is not None
        else None
    )
    if wrapper is None or wrapper.children or not wrapper.param_type.supports_children:
        return None
    if is_array and wrapper.param_type not in {
        ParameterType.ARRAY,
        ParameterType.ARRAY_OF_OBJECTS,
    }:
        return None
    if not is_array and wrapper.param_type is not ParameterType.OBJECT:
        return None

    child_rows = [
        row for index, row in enumerate(table.rows) if index != existing_index
    ]
    documented_names = {row.parameter.name for row in child_rows}
    if not child_rows or not example_fields.intersection(documented_names):
        return None

    anchor = (
        table.rows[existing_index].ref_anchor
        if existing_index is not None
        else None
    )
    if wrapper.param_type is ParameterType.ARRAY:
        wrapper.param_type = ParameterType.ARRAY_OF_OBJECTS
    table.rows = [TableRow(wrapper, anchor)]
    return TableExtraction(
        rows=child_rows,
        issues=[],
        fields_total=len(child_rows),
        fields_recognized=len(child_rows),
        fields_unknown_type=0,
        fields_failed=0,
    )
