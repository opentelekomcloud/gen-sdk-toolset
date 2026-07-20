from tools.scanner.parsers.docutils.inference import infer_documented_example_nesting
from tools.scanner.parsers.docutils.table import TableExtraction
from tools.shared.ir import Example, Parameter, ParameterType, Section, SectionName


def _table(*parameters: Parameter) -> TableExtraction:
    return TableExtraction(
        parameters=list(parameters),
        ref_anchors=[None] * len(parameters),
        issues=[],
        fields_total=len(parameters),
        fields_recognized=len(parameters),
        fields_unknown_type=0,
        fields_failed=0,
    )


def _request_example(parsed: dict) -> dict[SectionName, Section]:
    return {
        SectionName.EXAMPLE_REQUEST: Section(
            name=SectionName.EXAMPLE_REQUEST,
            examples=[Example(raw="", parsed=parsed)],
        )
    }


def test_reuses_documented_wrapper_from_another_table() -> None:
    name = Parameter(name="name", param_type=ParameterType.STRING)
    description = Parameter(name="description", param_type=ParameterType.STRING)
    wrapper = Parameter(
        name="widget",
        param_type=ParameterType.OBJECT,
        mandatory=True,
    )
    body = _table(name, description)
    labels = {}

    infer_documented_example_nesting(
        {SectionName.BODY: body},
        {"widget": wrapper},
        _request_example({"widget": {"name": "demo"}}),
        labels,
    )

    assert body.parameters == [wrapper]
    assert labels[SectionName.BODY]["widget"].parameters == [name, description]
    assert wrapper.mandatory is True


def test_moves_sibling_fields_under_existing_wrapper() -> None:
    wrapper = Parameter(name="widget", param_type=ParameterType.OBJECT)
    name = Parameter(name="name", param_type=ParameterType.STRING)
    body = _table(wrapper, name)
    labels = {}

    infer_documented_example_nesting(
        {SectionName.BODY: body},
        {},
        _request_example({"widget": {"name": "demo"}}),
        labels,
    )

    assert body.parameters == [wrapper]
    assert labels[SectionName.BODY]["widget"].parameters == [name]


def test_does_not_invent_wrapper_from_example() -> None:
    name = Parameter(name="name", param_type=ParameterType.STRING)
    body = _table(name)

    infer_documented_example_nesting(
        {SectionName.BODY: body},
        {},
        _request_example({"widget": {"name": "demo"}}),
        {},
    )

    assert body.parameters == [name]


def test_promotes_documented_array_when_example_confirms_object_items() -> None:
    wrapper = Parameter(name="widgets", param_type=ParameterType.ARRAY)
    name = Parameter(name="name", param_type=ParameterType.STRING)
    response = _table(wrapper, name)
    labels = {}

    infer_documented_example_nesting(
        {SectionName.RESPONSE: response},
        {},
        {
            SectionName.EXAMPLE_RESPONSE: Section(
                name=SectionName.EXAMPLE_RESPONSE,
                examples=[Example(raw="", parsed={"widgets": [{"name": "demo"}]})],
            )
        },
        labels,
    )

    assert response.parameters == [wrapper]
    assert wrapper.param_type is ParameterType.ARRAY_OF_OBJECTS
    assert labels[SectionName.RESPONSE]["widgets"].parameters == [name]


def test_groups_documented_array_children_inside_undocumented_json_wrapper() -> None:
    identifier = Parameter(name="id", param_type=ParameterType.STRING)
    links = Parameter(name="links", param_type=ParameterType.ARRAY)
    href = Parameter(name="href", param_type=ParameterType.STRING)
    rel = Parameter(name="rel", param_type=ParameterType.STRING)
    status = Parameter(name="status", param_type=ParameterType.STRING)
    response = _table(identifier, links, href, rel, status)
    labels = {}

    infer_documented_example_nesting(
        {SectionName.RESPONSE: response},
        {},
        {
            SectionName.EXAMPLE_RESPONSE: Section(
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
        },
        labels,
    )

    assert response.parameters == [identifier, links, status]
    assert links.param_type is ParameterType.ARRAY_OF_OBJECTS
    assert labels[SectionName.RESPONSE]["links"].parameters == [href, rel]


def test_binds_misnamed_explicit_reference_when_json_confirms_root() -> None:
    wrapper = Parameter(name="widgets", param_type=ParameterType.ARRAY)
    response = _table(wrapper)
    identifier = Parameter(name="id", param_type=ParameterType.STRING)
    name = Parameter(name="name", param_type=ParameterType.STRING)
    referenced = _table(identifier, name)
    labels = {}

    infer_documented_example_nesting(
        {SectionName.RESPONSE: response},
        {},
        {
            SectionName.EXAMPLE_RESPONSE: Section(
                name=SectionName.EXAMPLE_RESPONSE,
                examples=[
                    Example(
                        raw="",
                        parsed={"widgets": [{"id": "1", "name": "demo"}]},
                    )
                ],
            )
        },
        labels,
        {SectionName.RESPONSE: {"widget": referenced}},
    )

    assert wrapper.param_type is ParameterType.ARRAY_OF_OBJECTS
    assert labels[SectionName.RESPONSE]["widgets"] is referenced
