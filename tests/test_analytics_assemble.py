from tools.panel.core.analytics.assemble import assemble_nesting_from_examples
from tools.shared.ir import (
    Endpoint,
    Example,
    HttpMethod,
    Parameter,
    ParameterType,
    Section,
    SectionName,
)
from tools.shared.scan import SectionScanResult, SectionStatus


def _endpoint(*sections: Section) -> Endpoint:
    all_sections = {
        SectionName.PATH_PARAMS: Section(name=SectionName.PATH_PARAMS),
        SectionName.QUERY_PARAMS: Section(name=SectionName.QUERY_PARAMS),
        SectionName.HEADERS: Section(name=SectionName.HEADERS),
        SectionName.BODY: Section(name=SectionName.BODY),
        SectionName.RESPONSE: Section(name=SectionName.RESPONSE),
        SectionName.EXAMPLE_REQUEST: Section(name=SectionName.EXAMPLE_REQUEST),
        SectionName.EXAMPLE_RESPONSE: Section(name=SectionName.EXAMPLE_RESPONSE),
    }
    for section in sections:
        all_sections[section.name] = section

    return Endpoint(
        path="test.rst",
        method=HttpMethod.GET,
        uri="/test",
        sections=list(all_sections.values()),
    )


def test_moves_sibling_fields_under_existing_wrapper() -> None:
    wrapper = Parameter(name="widget", param_type=ParameterType.OBJECT)
    name = Parameter(name="name", param_type=ParameterType.STRING)
    body = Section(
        name=SectionName.BODY,
        parameters=[wrapper, name],
    )
    req = Section(
        name=SectionName.EXAMPLE_REQUEST,
        examples=[Example(raw="", parsed={"widget": {"name": "demo"}})],
    )

    endpoint = assemble_nesting_from_examples(_endpoint(body, req))

    new_body = next(s for s in endpoint.sections if s.name == SectionName.BODY)
    assert len(new_body.parameters) == 1
    assert new_body.parameters[0].name == "widget"
    assert len(new_body.parameters[0].children) == 1
    assert new_body.parameters[0].children[0].name == "name"


def test_promotes_documented_array_when_example_confirms_object_items() -> None:
    wrapper = Parameter(name="widgets", param_type=ParameterType.ARRAY)
    name = Parameter(name="name", param_type=ParameterType.STRING)
    response = Section(
        name=SectionName.RESPONSE,
        parameters=[wrapper, name],
    )
    ex = Section(
        name=SectionName.EXAMPLE_RESPONSE,
        examples=[Example(raw="", parsed={"widgets": [{"name": "demo"}]})],
    )

    endpoint = assemble_nesting_from_examples(_endpoint(response, ex))

    new_response = next(s for s in endpoint.sections if s.name == SectionName.RESPONSE)
    assert len(new_response.parameters) == 1
    assert new_response.parameters[0].name == "widgets"
    assert new_response.parameters[0].param_type is ParameterType.ARRAY_OF_OBJECTS
    assert len(new_response.parameters[0].children) == 1
    assert new_response.parameters[0].children[0].name == "name"


def test_groups_documented_array_children_inside_undocumented_json_wrapper() -> None:
    identifier = Parameter(name="id", param_type=ParameterType.STRING)
    links = Parameter(name="links", param_type=ParameterType.ARRAY)
    href = Parameter(name="href", param_type=ParameterType.STRING)
    rel = Parameter(name="rel", param_type=ParameterType.STRING)
    status = Parameter(name="status", param_type=ParameterType.STRING)

    response = Section(
        name=SectionName.RESPONSE,
        parameters=[identifier, links, href, rel, status],
    )
    ex = Section(
        name=SectionName.EXAMPLE_RESPONSE,
        examples=[
            Example(
                raw="",
                parsed={
                    "version": {
                        "id": "v2",
                        "links": [{"href": "/v2", "rel": "self"}],
                        "status": "CURRENT",
                    }
                },
            )
        ],
    )

    endpoint = assemble_nesting_from_examples(_endpoint(response, ex))

    new_response = next(s for s in endpoint.sections if s.name == SectionName.RESPONSE)

    assert len(new_response.parameters) == 1
    new_wrapper = new_response.parameters[0]
    assert new_wrapper.name == "version"
    assert new_wrapper.param_type is ParameterType.OBJECT

    param_names = {p.name for p in new_wrapper.children}
    assert param_names == {"id", "links", "status"}

    new_links = next(p for p in new_wrapper.children if p.name == "links")
    assert new_links.param_type is ParameterType.ARRAY_OF_OBJECTS

    child_names = {p.name for p in new_links.children}
    assert child_names == {"href", "rel"}


def test_binds_unmatched_table_as_root_wrapper() -> None:
    identifier = Parameter(name="id", param_type=ParameterType.STRING)
    name = Parameter(name="name", param_type=ParameterType.STRING)

    dummy = Parameter(name="dummy", param_type=ParameterType.STRING)

    response = Section(
        name=SectionName.RESPONSE,
        parameters=[dummy],
        scan_result=SectionScanResult(
            status=SectionStatus.OK,
            unmatched_tables={"widget_table": [identifier, name]},
            fields_total=0,
            fields_recognized=0,
            fields_unknown_type=0,
            fields_failed=0,
        ),
    )
    ex = Section(
        name=SectionName.EXAMPLE_RESPONSE,
        examples=[
            Example(
                raw="",
                parsed={"widget": {"id": "1", "name": "demo"}},
            )
        ],
    )

    endpoint = assemble_nesting_from_examples(_endpoint(response, ex))

    new_response = next(s for s in endpoint.sections if s.name == SectionName.RESPONSE)

    assert len(new_response.parameters) == 2
    assert new_response.parameters[0].name == "dummy"

    wrapper = new_response.parameters[1]
    assert wrapper.name == "widget"
    assert wrapper.param_type is ParameterType.OBJECT
    assert wrapper.mandatory is True
    assert wrapper.children == [identifier, name]
