"""Extract examples from docutils nodes and assemble example sections."""

from __future__ import annotations

import json
from collections.abc import Iterator

from docutils import nodes

from tools.shared.ir import Example, Parameter, ParameterType, Section, SectionName
from tools.shared.scan import Issue, IssueCode, SectionScanResult, SectionStatus

from .patterns import HTTP_PREFIX_RE
from .table import DETAILS_MAX, TableExtraction

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
        examples = sections.get(example_section)
        if table is None or examples is None:
            continue
        parsed_examples = _valid_parsed_examples(examples)
        if not parsed_examples:
            continue
        section_labels = label_tables.setdefault(parameter_section, {})
        root = _consistent_example_root(parsed_examples)
        if root is not None:
            root_name, is_array, example_fields = root
            nested_table = _apply_top_level_wrapper(
                table,
                wrapper_candidates.get(root_name),
                root_name=root_name,
                is_array=is_array,
                example_fields=example_fields,
            )
            if nested_table is not None:
                section_labels.setdefault(root_name, nested_table)
            _bind_referenced_root(
                table,
                root_name=root_name,
                is_array=is_array,
                example_fields=example_fields,
                candidates=(unmatched_reference_tables or {}).get(
                    parameter_section, {}
                ),
                label_tables=section_labels,
            )

        for documented_table in [table, *list(section_labels.values())]:
            _infer_nested_arrays(
                documented_table,
                parsed_examples,
                section_labels,
            )


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
        if len(documented.intersection(example_fields)) >= 2:
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
    return [
        example.parsed for example in section.examples if example.parsed
    ]


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
    for example in examples:
        for container in _object_nodes(example):
            if parent_name not in container:
                continue
            if len(documented_names.intersection(container)) < 2:
                continue
            value = container[parent_name]
            if not isinstance(value, list) or not value:
                return None
            if not all(isinstance(item, dict) for item in value):
                return None
            nested_names = set().union(*(set(item) for item in value))
            matches.append((nested_names & documented_names) - {parent_name})
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
    rows = list(zip(table.parameters, table.ref_anchors))
    child_rows = [
        (parameter, anchor)
        for parameter, anchor in rows
        if parameter is not parent and parameter.name in child_names
    ]
    if not child_rows:
        return None
    child_ids = {id(parameter) for parameter, _ in child_rows}
    table.parameters = [
        parameter for parameter, _ in rows if id(parameter) not in child_ids
    ]
    table.ref_anchors = [
        anchor for parameter, anchor in rows if id(parameter) not in child_ids
    ]
    return TableExtraction(
        parameters=[parameter for parameter, _ in child_rows],
        ref_anchors=[anchor for _, anchor in child_rows],
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
            for index, parameter in enumerate(table.parameters)
            if parameter.name == root_name
        ),
        None,
    )
    wrapper = (
        table.parameters[existing_index]
        if existing_index is not None
        else candidate
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

    children = [
        parameter
        for index, parameter in enumerate(table.parameters)
        if index != existing_index
    ]
    documented_names = {child.name for child in children}
    if not children or not example_fields.intersection(documented_names):
        return None

    child_anchors = [
        anchor
        for index, anchor in enumerate(table.ref_anchors)
        if index != existing_index
    ]
    anchor = table.ref_anchors[existing_index] if existing_index is not None else None
    if wrapper.param_type is ParameterType.ARRAY:
        wrapper.param_type = ParameterType.ARRAY_OF_OBJECTS
    table.parameters = [wrapper]
    table.ref_anchors = [anchor]
    return TableExtraction(
        parameters=children,
        ref_anchors=child_anchors,
        issues=[],
        fields_total=len(children),
        fields_recognized=len(children),
        fields_unknown_type=0,
        fields_failed=0,
    )


def extract_examples(section: nodes.section) -> list[Example]:
    """Return every code or literal block inside a section."""
    blocks: list[Example] = []
    visited: set[int] = set()

    for item in section.findall(nodes.list_item):
        label = _extract_item_label(item)
        for code in item.findall(nodes.literal_block):
            if id(code) in visited:
                continue
            visited.add(id(code))
            blocks.append(_make_example(code, label=label))

    for code in section.findall(nodes.literal_block):
        if id(code) in visited:
            continue
        visited.add(id(code))
        blocks.append(
            _make_example(
                code,
                label=_nearest_example_label(section, code),
            )
        )

    return blocks


def split_combined_examples(
    blocks: list[Example],
) -> tuple[list[Example], list[Example], list[Issue]]:
    request: list[Example] = []
    response: list[Example] = []
    guessed = False

    for block in blocks:
        label = (block.label or "").lower()
        if "response" in label:
            response.append(block)
        else:
            request.append(block)
            guessed = guessed or "request" not in label

    issues = []
    if guessed:
        issues.append(
            Issue(
                code=IssueCode.EXAMPLE_UNLABELED,
                location="combined example section",
                details="request/response split guessed (no labels)",
            )
        )
    return request, response, issues


def add_examples_to_section(
    sections: dict[SectionName, Section],
    name: SectionName,
    blocks: list[Example],
    *,
    extra_issues: list[Issue] | None = None,
) -> None:
    if not blocks:
        return

    issues = [*_example_json_issues(blocks), *(extra_issues or [])]
    existing = sections.get(name)
    if existing is not None:
        _extend_example_section(existing, blocks, issues)
        return

    sections[name] = _create_example_section(name, blocks, issues)


def _extract_item_label(item: nodes.list_item) -> str | None:
    p = next(iter(item.findall(nodes.paragraph)), None)
    if p is None:
        return None
    text = p.astext().strip()
    return text or None


def _nearest_example_label(
    section: nodes.section,
    block: nodes.literal_block,
) -> str | None:
    label = None
    for node in section.findall(nodes.Element):
        if node is block:
            break
        if not isinstance(node, nodes.paragraph):
            continue
        text = node.astext().strip()
        if _is_example_label(text):
            label = text
    return label


def _is_example_label(text: str) -> bool:
    normalized = text.lower()
    return (
        "example" in normalized or "sample" in normalized
    ) and ("request" in normalized or "response" in normalized)


def _make_example(block: nodes.literal_block, *, label: str | None) -> Example:
    raw = block.astext()
    return Example(
        raw=raw,
        language=_extract_language(block),
        parsed=_try_parse_json(raw),
        label=label,
    )


def _extract_language(block: nodes.literal_block) -> str | None:
    language = block.get("language")
    if language:
        return language
    return next(
        (name for name in block.get("classes", []) if name != "code"),
        None,
    )


def _try_parse_json(raw: str) -> dict | list | None:
    candidate = HTTP_PREFIX_RE.sub("", raw, count=1).strip()
    if not candidate:
        return None
    try:
        result = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(result, (dict, list)):
        return result
    return None


def _example_json_issues(blocks: list[Example]) -> list[Issue]:
    return [
        Issue(
            code=IssueCode.EXAMPLE_INVALID_JSON,
            location=f"example {index}",
            details=(block.label or "")[:DETAILS_MAX] or None,
        )
        for index, block in enumerate(blocks, start=1)
        if block.parsed is None and _expects_json(block)
    ]


def _expects_json(block: Example) -> bool:
    if block.language:
        return block.language.lower() in {"json", "application/json"}
    return block.raw.lstrip().startswith(("{", "["))


def _create_example_section(
    name: SectionName,
    blocks: list[Example],
    issues: list[Issue],
) -> Section:
    status = SectionStatus.PARTIAL if _has_invalid_example(issues) else SectionStatus.OK
    return Section(
        name=name,
        examples=list(blocks),
        scan_result=SectionScanResult(status=status, issues=issues),
    )


def _extend_example_section(
    section: Section,
    blocks: list[Example],
    issues: list[Issue],
) -> None:
    section.examples.extend(blocks)
    section.scan_result.issues.extend(issues)
    if _has_invalid_example(section.scan_result.issues):
        section.scan_result.status = SectionStatus.PARTIAL


def _has_invalid_example(issues: list[Issue]) -> bool:
    return any(issue.code is IssueCode.EXAMPLE_INVALID_JSON for issue in issues)
