"""Operation proposals for the endpoints already placed in one resource."""

import pytest

from tools.panel.core.action_selectors import ActionSelector
from tools.panel.core.operations import (
    NamingConflict,
    OperationKind,
    propose_operations,
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


def _doc(
    path: str,
    uri: str,
    method: HttpMethod = HttpMethod.POST,
    *,
    examples: tuple[dict, ...] = (),
    body: tuple[Parameter, ...] = (),
    query: tuple[Parameter, ...] = (),
    responses: tuple[dict, ...] = (),
) -> Endpoint:
    sections = {s: Section(name=s) for s in SectionName}
    sections[SectionName.BODY].parameters.extend(body)
    sections[SectionName.QUERY_PARAMS].parameters.extend(query)
    for section, values in (
        (SectionName.EXAMPLE_REQUEST, examples),
        (SectionName.EXAMPLE_RESPONSE, responses),
    ):
        sections[section].examples.extend(Example(raw="", parsed=v) for v in values)
    return Endpoint(path=path, uri=uri, method=method, sections=list(sections.values()))


# ---------------------------------------------------------------------------
# URI-only rules and final names within a single layout resource
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "uri", "kind", "name"),
    [
        (HttpMethod.GET, "/v1/{project}/vpcs", OperationKind.list, "list"),
        (HttpMethod.GET, "/v1/{project}/vpcs/%7Bid%7D", OperationKind.get, "get"),
        (HttpMethod.POST, "/v1/{project}/vpcs", OperationKind.create, "create"),
        (HttpMethod.PATCH, "/vpcs/{id}", OperationKind.update, "update"),
        (HttpMethod.PUT, "/vpcs/{id}", OperationKind.update, "update"),
        (HttpMethod.DELETE, "/vpcs/{id}", OperationKind.delete, "delete"),
        (
            HttpMethod.GET,
            "/svc/v1.0/{p}/vpcs/{id}/routes/?limit=2",
            OperationKind.list,
            "list_routes",
        ),
        (HttpMethod.GET, "/vpcs/{id}/status", OperationKind.get, "get_status"),
        (HttpMethod.GET, "/servers/detail", OperationKind.list, "list_detail"),
        (HttpMethod.GET, "/servers/{id}/detail", OperationKind.get, "get_detail"),
        (
            HttpMethod.GET,
            "/vpcs/{id}/access-keys",
            OperationKind.list,
            "list_access_keys",
        ),
        (HttpMethod.POST, "/vpcs/{id}/routes", OperationKind.create, "create_routes"),
        (HttpMethod.POST, "/vpcs/{id}/search", OperationKind.non_standard, "search"),
        (HttpMethod.POST, "/vpcs/{id}/unknown", OperationKind.non_standard, "unknown"),
        (HttpMethod.POST, "/vpcs/{id}", OperationKind.non_standard, "vpcs"),
        (
            HttpMethod.HEAD,
            "/v1/vpcs/{id}/OS-Keys/{key}",
            OperationKind.non_standard,
            "os_keys",
        ),
        (HttpMethod.OPTIONS, "/vpcs/{id}/class", OperationKind.non_standard, "class_"),
        (
            HttpMethod.OPTIONS,
            "/v1/vpcs/2%2FMore",
            OperationKind.non_standard,
            "op_2_more",
        ),
        (HttpMethod.GET, "/", OperationKind.list, "list"),
    ],
)
def test_uri_kind_and_python_name(method, uri, kind, name) -> None:
    [op] = propose_operations([_doc("source", uri, method)])
    assert (op.path, op.kind, op.proposed_name, op.conflict) == (
        "source",
        kind,
        name,
        None,
    )


def test_nameless_custom_endpoint_is_retained() -> None:
    [op] = propose_operations([_doc("root", "/v1/{id}", HttpMethod.HEAD)])
    assert (op.path, op.kind, op.proposed_name, op.conflict) == (
        "root",
        OperationKind.non_standard,
        None,
        NamingConflict.missing_name,
    )


def test_normalization_collision_on_distinct_uris_keeps_both_sources() -> None:
    docs = [_doc("b", "/r/search-by-tag"), _doc("a", "/r/search_by_tag")]
    ops = propose_operations(docs)
    assert [(op.path, op.proposed_name, op.conflict) for op in ops] == [
        (p, "search_by_tag", NamingConflict.duplicate_name) for p in ("a", "b")
    ]
    assert ops == propose_operations(docs[::-1])
    assert propose_operations([docs[0]])[0].conflict is None


def test_layout_can_place_distinct_uri_roots_in_one_resource() -> None:
    docs = [
        _doc(root, f"/{root}/{{id}}", HttpMethod.GET) for root in ("vpcs", "groups")
    ]
    assert [(op.proposed_name, op.conflict) for op in propose_operations(docs)] == [
        ("get_groups", None),
        ("get_vpcs", None),
    ]
    assert propose_operations(docs[::-1]) == propose_operations(docs)
    assert propose_operations(docs[:1])[0].proposed_name == "get"


# ---------------------------------------------------------------------------
# Terminal action selectors and incomplete scan evidence
# ---------------------------------------------------------------------------


def test_nova_actions_use_exact_request_keys_on_every_http_method() -> None:
    uri = "/v2.1/{project}/servers/{server}/action/?details=true"
    docs = [
        _doc(key, uri, HttpMethod.PUT, examples=({key: data},))
        for key, data in (
            ("addSecurityGroup", {"name": "web"}),
            ("removeSecurityGroup", {"name": "web"}),
            ("os-start", None),
            ("os-stop", {}),
        )
    ]
    ops = propose_operations(docs)
    assert {op.path: op.proposed_name for op in ops} == {
        "addSecurityGroup": "add_security_group",
        "removeSecurityGroup": "remove_security_group",
        "os-start": "start",
        "os-stop": "stop",
    }
    assert all(
        op.kind is OperationKind.non_standard and op.conflict is None for op in ops
    )
    assert all(op.selector == ActionSelector((op.path,)) for op in ops)
    renamed = [
        d.model_copy(update={"title": "New title", "api_version": "v8"}) for d in docs
    ]
    assert ops == propose_operations(renamed[::-1])


def test_two_values_on_one_document_are_two_stable_operations() -> None:
    doc = _doc(
        "tags",
        "/v1/things/{id}/tags/action",
        examples=(
            {"action": "delete", "tags": []},
            {"action": "create", "tags": []},
            {"action": "delete"},
        ),
    )
    ops = propose_operations([doc])
    assert [(op.proposed_name, op.selector, op.conflict) for op in ops] == [
        ("create_tags", ActionSelector(("action",), "create"), None),
        ("delete_tags", ActionSelector(("action",), "delete"), None),
    ]


@pytest.mark.parametrize(
    ("description", "names"),
    [
        (
            "Possible values are create and delete. Use delete to remove tags.",
            ["delete"],
        ),
        ("Enumeration values:\n\ncreate\n\ndelete", ["create", "delete"]),
        ("Range\n\ncreate\n\nDefault Value\n\nN/A", ["create"]),
        (
            "execute: Execute the policy.\n\npause: Pause the policy.",
            ["execute", "pause"],
        ),
        ("The value can be set to create or delete only.", ["create", "delete"]),
        ("The value is add, update, or remove.", ["add", "remove", "update"]),
        (
            "If action is set to count, count. If action is set to filter, list.",
            ["count", "filter"],
        ),
    ],
)
def test_schema_can_supply_an_action_without_parsed_examples(
    description, names
) -> None:
    field = Parameter(name="action", description=description)
    ops = propose_operations([_doc("actions", "/action", body=(field,))])
    assert [op.proposed_name for op in ops] == names
    assert all(op.conflict is None for op in ops)


def test_nested_dispatch_uses_the_distinguishing_key_and_parent() -> None:
    uri = "/v1/{project}/routetables/{id}/action"
    docs = [
        _doc(k, uri, examples=({"routetable": {"subnets": {k: ["id"]}}},))
        for k in ("associate", "disassociate")
    ]
    ops = propose_operations(docs)
    assert [(op.proposed_name, op.selector) for op in ops] == [
        (k + "_subnets", ActionSelector(("routetable", "subnets", k)))
        for k in ("associate", "disassociate")
    ]
    assert all(op.conflict is None for op in ops)
    assert ops == propose_operations(docs[::-1])
    assert propose_operations([docs[0]]) == [ops[0]]


def test_branching_envelope_with_new_keys_preserves_all_examples() -> None:
    doc = _doc(
        "expand",
        "/instances/{id}/action",
        examples=(
            {"expand_cluster": {"coordinators": []}},
            {"expand_cluster": {"shard": {"count": 2}}},
            {"enlarge_volume": {"size": 10}},
        ),
    )
    ops = propose_operations([doc])
    assert {op.proposed_name for op in ops} == {
        "expand_cluster_coordinators",
        "expand_cluster_shard",
        "enlarge_volume",
    }


def test_request_table_keeps_nested_command_siblings_with_partial_examples() -> None:
    commands = [
        Parameter(name=k, param_type=ParameterType.ARRAY)
        for k in ("associate", "disassociate")
    ]
    table = Parameter(
        name="routetable", children=[Parameter(name="subnets", children=commands)]
    )
    doc = _doc(
        "table",
        "/routetables/{id}/action",
        body=(table,),
        examples=(
            {"routetable": {"subnets": {"associate": ["id"]}}},
            {"os-stop": None},
        ),
    )
    assert {op.proposed_name for op in propose_operations([doc])} == {
        "associate_subnets",
        "disassociate_subnets",
        "stop",
    }


def test_body_table_can_name_an_action_without_using_response_evidence() -> None:
    length = Parameter(name="length")
    root = Parameter(name="os-getConsoleOutput", children=[length])
    (op,) = propose_operations(
        [
            _doc(
                "logs",
                "/servers/{id}/action",
                body=(root, length),
                responses=({"delete": {}},),
            )
        ]
    )
    assert (op.proposed_name, op.conflict) == ("get_console_output", None)


def test_unknown_or_partial_selector_keeps_its_source_and_reason() -> None:
    uri = "/servers/{id}/action"
    docs = [
        _doc("missing", uri, responses=({"os-start": None},)),
        _doc("ambiguous", uri, examples=({"name": "a", "id": 1},)),
        _doc("partial", uri, examples=({"action": "enable"}, {"action": ["disable"]})),
    ]
    ops = propose_operations(docs)
    assert [(op.path, op.proposed_name, op.conflict) for op in ops] == [
        ("ambiguous", None, NamingConflict.ambiguous_action_selector),
        ("missing", None, NamingConflict.missing_action_selector),
        ("partial", "enable_servers", None),
        ("partial", None, NamingConflict.ambiguous_action_selector),
    ]


def test_distinct_selectors_that_normalize_to_one_name_are_preserved() -> None:
    doc = _doc("one", "/servers/action", examples=({"os-start": {}}, {"start": {}}))
    ops = propose_operations([doc])
    assert {op.selector for op in ops} == {
        ActionSelector(("os-start",)),
        ActionSelector(("start",)),
    }
    assert all(
        op.proposed_name == "start" and op.conflict is NamingConflict.duplicate_name
        for op in ops
    )


def test_named_envelopes_and_action_values_on_one_source_both_survive() -> None:
    doc = _doc(
        "mixed",
        "/servers/action",
        body=(Parameter(name="action"),),
        examples=({"action": "enable"}, {"quiesce": {}}, {"os-stop": None}),
    )
    assert [(op.proposed_name, op.conflict) for op in propose_operations([doc])] == [
        ("enable_servers", None),
        ("stop", None),
        ("quiesce", None),
    ]


def test_different_scalar_arguments_do_not_establish_action_names() -> None:
    docs = [
        _doc(key, "/servers/action", examples=({key: "x"},)) for key in ("id", "name")
    ]
    ops = propose_operations(docs)
    assert [(op.path, op.conflict) for op in ops] == [
        ("id", NamingConflict.ambiguous_action_selector),
        ("name", NamingConflict.ambiguous_action_selector),
    ]


def test_misplaced_error_example_does_not_introduce_an_action() -> None:
    doc = _doc(
        "extend",
        "/volumes/action",
        body=(Parameter(name="os-extend"),),
        examples=({"badRequest": {"code": "400", "message": "Bad request"}},),
    )
    [op] = propose_operations([doc])
    assert (op.proposed_name, op.conflict) == ("extend", None)


def test_unparsed_example_keeps_a_conflict_alongside_a_known_request() -> None:
    doc = _doc("volume", "/volumes/action", body=(Parameter(name="os-extend"),))
    section = next(s for s in doc.sections if s.name is SectionName.EXAMPLE_REQUEST)
    section.examples.append(Example(raw="POST https://{ECS Endpoint}/volumes/action"))
    assert [op.proposed_name for op in propose_operations([doc])] == ["extend"]
    section.examples.append(
        Example(
            raw="POST /v2/volumes/action\nPOST /v2.1/volumes/action\n\n"
            '{"os-detach": null}'
        )
    )
    section.examples.append(Example(raw="{invalid"))
    assert [(op.proposed_name, op.conflict) for op in propose_operations([doc])] == [
        ("detach", None),
        ("extend", None),
        (None, NamingConflict.ambiguous_action_selector),
    ]


def test_query_dispatch_keeps_the_source_field_and_fixed_value() -> None:
    field = Parameter(
        name="action-id", description="reject: Reject it.\nresolve: Approve it."
    )
    uri = "/applications/{id}/action"
    doc = _doc("apply", uri, query=(field,), examples=({"ids": ["1"], "msg": "yes"},))
    ops = propose_operations([doc])
    assert [(op.proposed_name, op.selector) for op in ops] == [
        (
            value + "_applications",
            ActionSelector(("action-id",), value, SectionName.QUERY_PARAMS),
        )
        for value in ("reject", "resolve")
    ]
    [fixed] = propose_operations(
        [doc.model_copy(update={"uri": uri + "?action-id=reject"})]
    )
    assert fixed == ops[0]
