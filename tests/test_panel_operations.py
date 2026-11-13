"""The default kind and SDK method name of a resource's operations (ISS-0090).

Pure tests: the input is hand-built IR for the endpoints of one layout resource.
"""

import random

import pytest

from tools.panel.core.operations import (
    MissingName,
    OperationKind,
    propose_operations,
)
from tools.shared.ir import Endpoint, HttpMethod, Section, SectionName

GET, POST, PUT = HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT
PATCH, DELETE = HttpMethod.PATCH, HttpMethod.DELETE


def _doc(
    method: HttpMethod, uri: str, path: str | None = None, title: str = ""
) -> Endpoint:
    return Endpoint(
        path=path or f"{method.value} {uri}",
        title=title,
        method=method,
        uri=uri,
        sections=[Section(name=name) for name in SectionName],
    )


def _proposed(*docs: Endpoint) -> dict[str, tuple[OperationKind, str | None]]:
    return {op.path: (op.kind, op.name) for op in propose_operations(docs)}


def _names(*docs: Endpoint) -> list[str | None]:
    proposed = _proposed(*docs)
    return [proposed[doc.path][1] for doc in docs]


def _missing(*docs: Endpoint) -> list[MissingName | None]:
    reasons = {op.path: op.missing_name for op in propose_operations(docs)}
    return [reasons[doc.path] for doc in docs]


VPCS = "/v1/{project_id}/vpcs"
TAGS = "/v2.1/{project_id}/servers/{server_id}/tags"

# ---------------------------------------------------------------------------
# Kind: base only on a collection and its item
# ---------------------------------------------------------------------------


def test_collection_and_item_of_the_resource_are_base():
    assert _proposed(
        _doc(GET, VPCS),
        _doc(POST, VPCS),
        _doc(GET, f"{VPCS}/{{vpc_id}}"),
        _doc(PUT, f"{VPCS}/{{vpc_id}}"),
        _doc(DELETE, f"{VPCS}/{{vpc_id}}"),
    ) == {
        f"GET {VPCS}": (OperationKind.list, "list"),
        f"POST {VPCS}": (OperationKind.create, "create"),
        f"GET {VPCS}/{{vpc_id}}": (OperationKind.get, "get"),
        f"PUT {VPCS}/{{vpc_id}}": (OperationKind.update, "update"),
        f"DELETE {VPCS}/{{vpc_id}}": (OperationKind.delete, "delete"),
    }


def test_patch_on_an_item_is_update():
    [op] = propose_operations([_doc(PATCH, "/v1/vpcs/{id}")])
    assert (op.kind, op.name) == (OperationKind.update, "update")


def test_nested_collection_is_base():
    assert _proposed(
        _doc(GET, TAGS),
        _doc(POST, TAGS),
        _doc(GET, f"{TAGS}/{{tag}}"),
        _doc(PUT, f"{TAGS}/{{tag}}"),
        _doc(DELETE, f"{TAGS}/{{tag}}"),
    ) == {
        f"GET {TAGS}": (OperationKind.list, "list_tags"),
        f"POST {TAGS}": (OperationKind.create, "create_tag"),
        f"GET {TAGS}/{{tag}}": (OperationKind.get, "get_tag"),
        f"PUT {TAGS}/{{tag}}": (OperationKind.update, "update_tag"),
        f"DELETE {TAGS}/{{tag}}": (OperationKind.delete, "delete_tag"),
    }


@pytest.mark.parametrize(
    ("method", "uri"),
    [
        (PUT, "/v2.0/vpc/peerings/{peering_id}/accept"),
        (POST, "/v1/{project_id}/routetables/{routetable_id}/action"),
        (GET, "/v1/{project_id}/antiddos/{floating_ip_id}/status"),
        (GET, "/v2.0/{project_id}/publicips/tags"),
        (POST, "/v3/{project_id}/backups/create"),
        (GET, "/v2/apigw/gateway-responses/{response_id}/{response_type}"),
        (GET, "/{api_version}"),
    ],
)
def test_other_shapes_are_custom(method, uri):
    [op] = propose_operations([_doc(method, uri)])
    assert op.kind is OperationKind.custom


def test_a_word_is_a_collection_only_with_an_item_in_the_resource():
    events = "/v2/{project_id}/training-jobs/{job_id}/events"
    alone = _proposed(_doc(GET, events))
    with_item = _proposed(_doc(GET, events), _doc(GET, f"{events}/{{event_id}}"))
    assert alone[f"GET {events}"] == (OperationKind.custom, "events")
    assert with_item[f"GET {events}"] == (OperationKind.list, "list_events")


def test_put_and_delete_on_a_whole_collection_are_custom():
    proposed = _proposed(
        _doc(PUT, TAGS), _doc(DELETE, TAGS), _doc(DELETE, f"{TAGS}/{{tag}}")
    )
    assert proposed[f"PUT {TAGS}"] == (OperationKind.custom, "put_tags")
    assert proposed[f"DELETE {TAGS}"] == (OperationKind.custom, "delete_tags")
    assert proposed[f"DELETE {TAGS}/{{tag}}"] == (OperationKind.delete, "delete_tag")


def test_post_on_an_item_is_custom():
    eip = "/v2/{project_id}/clusters/{cluster_id}/eips/{eip_id}"
    assert _proposed(_doc(POST, eip))[f"POST {eip}"] == (OperationKind.custom, "eips")


# ---------------------------------------------------------------------------
# Default name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("collection", "name"),
    [
        ("tags", "delete_tag"),
        ("security-policies", "delete_security_policy"),
        ("api-groups", "delete_api_group"),
        ("policy", "delete_policy"),
        ("address", "delete_address"),
        ("addresses", "delete_address"),
        ("mailboxes", "delete_mailbox"),
        ("status", "delete_status"),
        ("diagnosis", "delete_diagnosis"),
        ("autosearch-parameter-analysis", "delete_autosearch_parameter_analysis"),
        ("apis", "delete_api"),
        ("switches", "delete_switch"),
        ("caches", "delete_cache"),
        ("aliases", "delete_alias"),
        ("ip-aliases", "delete_ip_alias"),
        ("databases", "delete_database"),
        ("releases", "delete_release"),
        ("gateway-responses", "delete_gateway_response"),
        ("ipaddresses", "delete_ipaddress"),
        ("business", "delete_business"),
        ("switch-status", "delete_switch_status"),
        ("metadata", "delete_metadata"),
    ],
)
def test_item_operation_names_its_collection_in_the_singular(collection, name):
    uri = f"/v1/servers/{{id}}/{collection}/{{item_id}}"
    assert _names(_doc(DELETE, uri)) == [name]


def test_list_keeps_the_collection_name_as_written():
    routes = "/v1/vpcs/{id}/routes"
    assert _names(_doc(GET, routes), _doc(GET, f"{routes}/{{route_id}}")) == [
        "list_routes",
        "get_route",
    ]


def test_custom_name_joins_the_segments_after_the_resource_segment():
    assert _names(
        _doc(PUT, "/v3/{project_id}/instances/{id}/backups/policy/update"),
        _doc(POST, "/v1/{project_id}/vpcs/{id}/tags/action"),
    ) == ["backups_policy_update", "tags_action"]


def test_custom_operation_on_the_resource_segment_takes_its_name():
    assert _names(_doc(POST, "/v1/{project_id}/quotas")) == ["quotas"]


@pytest.mark.parametrize(
    ("segment", "name"),
    [
        ("rolling-restart", "rolling_restart"),
        ("resizeVolume", "resize_volume"),
        ("2fa", "op_2fa"),
        ("import", "import_"),
    ],
)
def test_name_is_a_python_identifier(segment, name):
    assert _names(_doc(POST, f"/v1/clusters/{{id}}/{segment}")) == [name]


def test_version_segment_prefix_and_query_string_do_not_reach_the_name():
    uri = "/autoscaling-api/v1/{project_id}/groups/{id}/policies?limit=2"
    assert _names(_doc(GET, uri), _doc(GET, uri.replace("?", "/{pid}?"))) == [
        "list_policies",
        "get_policy",
    ]


def test_only_method_and_uri_affect_the_proposal():
    uri = "/v1/{project_id}/vpcs/{id}/accept"
    one = propose_operations([_doc(PUT, uri, "a.rst", "Accepting a Peering")])
    other = propose_operations([_doc(PUT, uri, "a.rst", "Reworded title")])
    assert one == other


def test_result_does_not_depend_on_input_order():
    docs = [
        _doc(GET, TAGS),
        _doc(PUT, TAGS),
        _doc(DELETE, TAGS),
        _doc(DELETE, f"{TAGS}/{{tag}}"),
        _doc(POST, f"{TAGS}/action", "add.rst"),
        _doc(POST, f"{TAGS}/action", "delete.rst"),
    ]
    expected = propose_operations(docs)
    for seed in range(5):
        shuffled = docs[:]
        random.Random(seed).shuffle(shuffled)
        assert propose_operations(shuffled) == expected


# ---------------------------------------------------------------------------
# Names that coincide within the resource
# ---------------------------------------------------------------------------


def test_documents_of_one_method_and_uri_get_no_name():
    action = "/v1/{project_id}/routetables/{routetable_id}/action"
    assert _names(
        _doc(POST, action, "associate.rst"),
        _doc(POST, action + "/", "disassociate.rst"),
        _doc(POST, action + "?dry_run=true", "dry_run.rst"),
    ) == [None, None, None]


def test_documents_of_one_base_call_get_no_name_and_keep_their_kind():
    instances = "/v3/{project_id}/instances"
    proposed = _proposed(
        _doc(POST, instances, "create.rst"),
        _doc(POST, instances, "restore.rst"),
        _doc(GET, f"{instances}/{{id}}"),
    )
    assert proposed["create.rst"] == (OperationKind.create, None)
    assert proposed["restore.rst"] == (OperationKind.create, None)
    assert proposed[f"GET {instances}/{{id}}"] == (OperationKind.get, "get")


def test_custom_names_on_one_uri_get_the_http_method():
    switch = "/v1/{project_id}/ips/switch"
    assert _names(_doc(GET, switch), _doc(POST, switch)) == [
        "get_switch",
        "post_switch",
    ]


@pytest.mark.parametrize(
    ("method", "custom"), [(POST, "post_delete"), (DELETE, "delete_delete")]
)
def test_base_name_stays_when_a_custom_name_coincides_with_it(method, custom):
    rules = "/v2/{project_id}/alarm-rules"
    assert _names(
        _doc(DELETE, f"{rules}/{{rule_id}}"),
        _doc(method, f"{rules}/delete"),
        _doc(GET, rules),
    ) == ["delete", custom, "list"]


def test_patch_next_to_put_on_one_item_is_named_patch():
    pod, tag = "/v2/pods/{name}", "/v2/pods/{name}/tags/{tag}"
    docs = [_doc(PUT, pod), _doc(PATCH, pod), _doc(PUT, tag), _doc(PATCH, tag)]
    assert _names(*docs) == ["update", "patch", "update_tag", "patch_tag"]
    assert {op.kind for op in propose_operations(docs)} == {OperationKind.update}


def test_patch_without_a_put_on_its_item_stays_update():
    rules = "/v1/rules"
    assert _names(
        _doc(PATCH, f"{rules}/{{id}}"),
        _doc(POST, f"{rules}/update"),
        _doc(PUT, f"{rules}/{{id}}/tags/{{tag}}"),
    ) == ["update", "post_update", "update_tag"]


def test_custom_name_gives_way_to_the_final_base_name():
    rules = "/v1/rules"
    assert _names(
        _doc(PUT, f"{rules}/{{id}}"),
        _doc(PATCH, f"{rules}/{{id}}"),
        _doc(POST, f"{rules}/patch"),
    ) == ["update", "patch", "post_patch"]


def test_base_name_stays_when_a_prefixed_custom_name_reaches_it():
    policy = "/v1/servers/{id}/policy"
    docs = [
        _doc(DELETE, f"{policy}/{{policy_id}}"),
        _doc(DELETE, policy),
        _doc(PUT, policy),
    ]
    assert _names(*docs) == ["delete_policy", None, "put_policy"]
    assert _missing(*docs) == [None, MissingName.name_conflict, None]


def test_names_that_still_coincide_are_left_empty():
    assert _names(
        _doc(GET, "/v3/{project_id}/backups"),
        _doc(GET, "/v3/{project_id}/backups/{id}"),
        _doc(GET, "/mysql/v3/{project_id}/backups"),
        _doc(POST, "/v1/{project_id}/clusters/{id}/rolling-restart"),
        _doc(POST, "/v1/{project_id}/clusters/{id}/rolling_restart"),
    ) == [None, "get", None, None, None]


def test_missing_name_says_why():
    action = "/v1/{project_id}/routetables/{routetable_id}/action"
    assert _missing(
        _doc(POST, action, "associate.rst"),
        _doc(POST, action, "disassociate.rst"),
        _doc(GET, "/v1/{project_id}/routetables/tags"),
        _doc(GET, "/v1/{project_id}/routetables/{resource_type}/tags"),
        _doc(GET, "/{api_version}"),
        _doc(GET, "/v1/{project_id}/routetables"),
    ) == [
        MissingName.same_call,
        MissingName.same_call,
        MissingName.name_conflict,
        MissingName.name_conflict,
        MissingName.no_segment,
        None,
    ]


def test_uri_without_a_constant_segment_gets_no_name():
    [op] = propose_operations([_doc(GET, "/{api_version}")])
    assert (op.kind, op.name) == (OperationKind.custom, None)
