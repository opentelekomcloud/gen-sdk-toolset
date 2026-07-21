"""Rebuild example-proven nesting over a scan result on demand.

Designed for human-in-the-loop workflows: if a user confirms that the parsed
example is structurally more accurate than the documented tables, this module
uses the example to reconstruct the nested structure and create the Endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator

from tools.shared.ir import (
    Endpoint,
    Parameter,
    ParameterType,
    Section,
    SectionName,
)

PROOF_SECTIONS = {
    SectionName.BODY: SectionName.EXAMPLE_REQUEST,
    SectionName.RESPONSE: SectionName.EXAMPLE_RESPONSE,
}


def example_root(parsed_examples: list[dict | list]) -> tuple[str, set[str]] | None:
    """Return the single wrapper ``(name, field_names)`` proven by the examples.

    An example proves a top-level wrapper only when every parsed example is a
    one-key object (or a list of such objects) sharing the same root key. The
    returned field set is the union of the fields seen under that key.

    :param parsed_examples: A list of parsed JSON objects/arrays.
    """
    roots: list[tuple[str, set[str]]] = []
    for parsed in parsed_examples:
        if not isinstance(parsed, dict) or len(parsed) != 1:
            return None
        name, value = next(iter(parsed.items()))
        if isinstance(value, dict):
            roots.append((name, set(value)))
        elif (
            isinstance(value, list)
            and value
            and all(isinstance(item, dict) for item in value)
        ):
            roots.append((name, set().union(*(set(item) for item in value))))
        else:
            return None
    if not roots:
        return None
    name = roots[0][0]
    if any(root_name != name for root_name, _ in roots):
        return None
    return name, set().union(*(fields for _, fields in roots))


def assemble_nesting_from_examples(endpoint: Endpoint) -> Endpoint:
    """Return a copy of ``endpoint`` with body/response fields wrapped.

    For each (parameter section, example section) pair, if the example proves a
    single wrapper object whose fields overlap the documented fields — and that
    wrapper is not already a documented row — the flat fields are moved under a
    synthesized wrapper parameter. The input is never mutated; the raw scan
    result stays intact so callers can toggle between raw and assembled views.

    :param endpoint: The scanned endpoint IR to process.
    """
    endpoint = endpoint.model_copy(deep=True)
    sections = {section.name: section for section in endpoint.sections}
    for parameter_name, example_name in PROOF_SECTIONS.items():
        _wrap_section(sections.get(parameter_name), sections.get(example_name))
    return endpoint


def _wrap_section(section: Section | None, example_section: Section | None) -> None:
    if section is None or example_section is None or not section.parameters:
        return
    parsed_examples = [
        example.parsed for example in example_section.examples if example.parsed
    ]
    if not parsed_examples:
        return

    _infer_arrays(section.parameters, parsed_examples)

    root = example_root(parsed_examples)
    if root is None:
        return
    root_name, example_fields = root
    documented = {parameter.name for parameter in section.parameters}

    if root_name not in documented:
        _synthesize_wrapper(section, root_name, example_fields, documented)
    else:
        _group_siblings_under_wrapper(section, root_name)


def _synthesize_wrapper(
    section: Section, root_name: str, example_fields: set[str], documented: set[str]
) -> None:
    """Wrap the section's fields under a synthesized ``root_name`` object.

    Children come from a referenced (unmatched) table when one matches the
    example; otherwise the whole documented table is nested under the wrapper.
    """
    unmatched_children = _find_matching_unmatched_table(section, example_fields)
    if unmatched_children is not None:
        _wrap_parameters(section, root_name, unmatched_children)
        return

    if example_fields & documented:
        # The example only proves the wrapper exists (and may enumerate just a
        # subset of fields); the full child set is the whole documented table.
        _wrap_parameters(section, root_name, list(section.parameters))


def _wrap_parameters(
    section: Section, root_name: str, children: list[Parameter]
) -> None:
    """Move ``children`` under a new ``root_name`` object parameter.

    Any existing top-level parameter whose name matches a wrapper child is
    dropped, so a field never appears both flat and nested. Unrelated
    parameters keep their order; the wrapper is appended at the end.
    """
    child_names = {child.name for child in children}
    remaining = [p for p in section.parameters if p.name not in child_names]
    remaining.append(
        Parameter(
            name=root_name,
            param_type=ParameterType.OBJECT,
            mandatory=True,
            description="",
            children=children,
        )
    )
    section.parameters = remaining


def _group_siblings_under_wrapper(section: Section, root_name: str) -> None:
    root_param = next(p for p in section.parameters if p.name == root_name)
    if root_param.children:
        return

    siblings = [p for p in section.parameters if p.name != root_name]
    if not siblings:
        return

    if root_param.param_type == ParameterType.ARRAY:
        root_param.param_type = ParameterType.ARRAY_OF_OBJECTS
    root_param.children = siblings
    sibling_ids = {id(s) for s in siblings}
    section.parameters = [p for p in section.parameters if id(p) not in sibling_ids]


def _find_matching_unmatched_table(
    section: Section, example_fields: set[str]
) -> list[Parameter] | None:
    if not section.scan_result or not section.scan_result.unmatched_tables:
        return None
    for candidates in section.scan_result.unmatched_tables.values():
        candidate_names = {p.name for p in candidates}
        if example_fields and example_fields.issubset(candidate_names):
            return list(candidates)
    return None


def _infer_arrays(
    parameters: list[Parameter], parsed_examples: list[dict | list]
) -> None:
    documented_names = {parameter.name for parameter in parameters}
    for parameter in list(parameters):
        if (
            parameter.param_type
            not in {ParameterType.ARRAY, ParameterType.ARRAY_OF_OBJECTS}
            or parameter.children
        ):
            continue
        child_names = _documented_array_children(
            parameter.name, documented_names, parsed_examples
        )
        if not child_names:
            continue

        children = [
            p for p in parameters if p is not parameter and p.name in child_names
        ]
        if not children:
            continue

        child_ids = {id(p) for p in children}
        parameters[:] = [p for p in parameters if id(p) not in child_ids]

        parameter.param_type = ParameterType.ARRAY_OF_OBJECTS
        parameter.children = children


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
