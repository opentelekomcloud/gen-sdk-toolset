"""Post-hoc example checks: assemble nesting and flag undocumented wrappers."""

from __future__ import annotations

from tools.panel.core.analytics import (
    assemble_nesting_from_examples,
    example_documentation_issues,
)
from tools.shared.ir import (
    Endpoint,
    Example,
    HttpMethod,
    Parameter,
    ParameterType,
    Section,
    SectionName,
)
from tools.shared.scan import (
    DocumentScanResult,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)


def _section(
    name: SectionName,
    *,
    parameters: list[Parameter] | None = None,
    examples: list[Example] | None = None,
) -> Section:
    parameters = parameters or []
    examples = examples or []
    has_data = bool(parameters or examples)
    total = len(parameters)
    return Section(
        name=name,
        parameters=parameters,
        examples=examples,
        scan_result=SectionScanResult(
            status=SectionStatus.OK if has_data else SectionStatus.MISSING,
            fields_total=total,
            fields_recognized=total,
        ),
    )


def _endpoint(
    *,
    body: list[Parameter] | None = None,
    request_example: object | None = None,
) -> Endpoint:
    overrides = {}
    if body is not None:
        overrides[SectionName.BODY] = _section(SectionName.BODY, parameters=body)
    if request_example is not None:
        overrides[SectionName.EXAMPLE_REQUEST] = _section(
            SectionName.EXAMPLE_REQUEST,
            examples=[Example(raw="{}", parsed=request_example)],
        )
    sections = [overrides.get(name, _section(name)) for name in SectionName]
    return Endpoint(
        path="creating_a_connection.rst",
        method=HttpMethod.POST,
        uri="/v2.0/dcaas/direct-connects",
        sections=sections,
        scan_result=DocumentScanResult(),
    )


_REQUEST_EXAMPLE = {"direct_connect": {"tenant_id": "x", "name": "y", "bandwidth": 2}}


def _flat_fields() -> list[Parameter]:
    return [
        Parameter(name="tenant_id", param_type=ParameterType.STRING),
        Parameter(name="name", param_type=ParameterType.STRING),
        Parameter(name="bandwidth", param_type=ParameterType.INTEGER),
    ]


def _body(endpoint: Endpoint) -> Section:
    return next(s for s in endpoint.sections if s.name is SectionName.BODY)


def test_assemble_wraps_flat_fields_under_example_root() -> None:
    endpoint = _endpoint(
        body=_flat_fields(),
        request_example=_REQUEST_EXAMPLE,
    )

    assembled = assemble_nesting_from_examples(endpoint)

    body = _body(assembled)
    assert [p.name for p in body.parameters] == ["direct_connect"]
    wrapper = body.parameters[0]
    assert wrapper.param_type is ParameterType.OBJECT
    assert [c.name for c in wrapper.children] == ["tenant_id", "name", "bandwidth"]


def test_assemble_does_not_mutate_the_input() -> None:
    endpoint = _endpoint(
        body=_flat_fields(),
        request_example=_REQUEST_EXAMPLE,
    )

    assemble_nesting_from_examples(endpoint)

    # original is untouched: still the three flat fields
    assert [p.name for p in _body(endpoint).parameters] == [
        "tenant_id",
        "name",
        "bandwidth",
    ]


def test_assemble_is_noop_without_a_matching_example() -> None:
    endpoint = _endpoint(body=_flat_fields(), request_example=None)

    assembled = assemble_nesting_from_examples(endpoint)

    assert [p.name for p in _body(assembled).parameters] == [
        "tenant_id",
        "name",
        "bandwidth",
    ]


def test_assemble_is_noop_when_example_root_is_a_documented_field() -> None:
    # The example root matches a documented field, so it is not a wrapper.
    body = [Parameter(name="direct_connect", param_type=ParameterType.OBJECT)]
    endpoint = _endpoint(body=body, request_example={"direct_connect": {"x": 1}})

    assembled = assemble_nesting_from_examples(endpoint)

    assert [p.name for p in _body(assembled).parameters] == ["direct_connect"]


def test_validate_flags_nesting_only_in_example() -> None:
    endpoint = _endpoint(
        body=_flat_fields(),
        request_example=_REQUEST_EXAMPLE,
    )

    issues = example_documentation_issues(endpoint)

    assert set(issues) == {SectionName.BODY}
    (issue,) = issues[SectionName.BODY]
    assert issue.code is IssueCode.NESTING_ONLY_IN_EXAMPLE
    assert issue.location == "direct_connect"


def test_validate_silent_when_documentation_matches_example() -> None:
    # Wrapper is a documented field -> the tables agree with the example.
    body = [Parameter(name="direct_connect", param_type=ParameterType.OBJECT)]
    endpoint = _endpoint(body=body, request_example={"direct_connect": {"x": 1}})

    assert example_documentation_issues(endpoint) == {}


def test_validate_flags_flat_siblings_under_documented_wrapper() -> None:
    # Wrapper is documented but its items are incorrectly listed as flat siblings.
    body = [
        Parameter(name="direct_connect", param_type=ParameterType.OBJECT),
        Parameter(name="tenant_id", param_type=ParameterType.STRING),
    ]
    endpoint = _endpoint(body=body, request_example=_REQUEST_EXAMPLE)

    issues = example_documentation_issues(endpoint)

    assert set(issues) == {SectionName.BODY}
    (issue,) = issues[SectionName.BODY]
    assert issue.code is IssueCode.NESTING_ONLY_IN_EXAMPLE
    assert issue.location == "direct_connect"
    assert issue.details == (
        "example wraps fields under 'direct_connect', but the "
        "documentation tables list them as flat siblings"
    )
