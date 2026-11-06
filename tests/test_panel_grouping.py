"""The preliminary grouping of endpoints into resources (ISS-0031).

Pure tests: no database - the input is hand-built IR, the way the active
snapshot's endpoint documents deserialize, or an unsaved document row.
"""

import re

import pytest
from pydantic import ValidationError

from tools.panel.core.analytics import analyze_document
from tools.panel.core.analytics.snapshot import OverallStatus
from tools.panel.core.db.models import DocumentRecord
from tools.panel.core.grouping import (
    RESOURCE_NAME_PATTERN,
    EndpointGrouping,
    GroupedResource,
    NotAnEndpointError,
    VersionGroup,
    group_endpoints,
)
from tools.shared.ir import (
    ENDPOINT_KIND,
    Document,
    Endpoint,
    HttpMethod,
    Section,
    SectionName,
)
from tools.shared.scan import (
    DocumentScanResult,
    Issue,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _endpoint(
    path: str,
    uri: str,
    api_version: str | None = "v1",
    *,
    body: SectionScanResult | None = None,
) -> Endpoint:
    return Endpoint(
        path=f"api-ref/source/{path}.rst",
        method=HttpMethod.GET,
        uri=uri,
        api_version=api_version,
        sections=[
            Section(
                name=name,
                scan_result=(
                    body
                    if body is not None and name is SectionName.BODY
                    else SectionScanResult(status=SectionStatus.MISSING)
                ),
            )
            for name in SectionName
        ],
        scan_result=DocumentScanResult(),
    )


def _row(
    path: str, uri: str | None, api_version: str | None, *, kind: str = ENDPOINT_KIND
) -> DocumentRecord:
    """An unsaved document row: its projected columns set, no payload."""
    return DocumentRecord(kind=kind, path=_path(path), uri=uri, api_version=api_version)


def _path(name: str) -> str:
    return f"api-ref/source/{name}.rst"


def _resources(grouping: EndpointGrouping, version: str) -> dict[str, list[str]]:
    """The resources of one version, by name."""
    [group] = [g for g in grouping.versions if g.api_version == version]
    return {resource.name: resource.endpoints for resource in group.resources}


def _unassigned(grouping: EndpointGrouping, version: str) -> list[str]:
    [group] = [g for g in grouping.versions if g.api_version == version]
    return group.unassigned


def _name_of(uri: str, api_version: str = "v1") -> str:
    """The single resource name the rule gives one endpoint."""
    grouping = group_endpoints([_endpoint("one", uri, api_version)])
    [name] = _resources(grouping, api_version)
    return name


# ---------------------------------------------------------------------------
# The first constant segment after the version
# ---------------------------------------------------------------------------


def test_endpoints_with_the_same_first_segment_share_a_resource() -> None:
    grouping = group_endpoints(
        [
            _endpoint("list", "/v1/{project_id}/servers"),
            _endpoint("show", "/v1/{project_id}/servers/{server_id}"),
        ]
    )

    assert _resources(grouping, "v1") == {"servers": [_path("list"), _path("show")]}
    assert _unassigned(grouping, "v1") == []
    assert grouping.no_version == []


def test_later_constant_segments_do_not_split_a_resource() -> None:
    grouping = group_endpoints(
        [
            _endpoint("list", "/v1/{project_id}/servers"),
            _endpoint("action", "/v1/{project_id}/servers/{server_id}/action"),
        ]
    )

    assert _resources(grouping, "v1") == {"servers": [_path("action"), _path("list")]}


def test_path_parameters_before_the_segment_are_skipped() -> None:
    assert _name_of("/v2/{project_id}/{domain_id}/zones") == "zones"


def test_segments_before_the_version_segment_are_not_the_resource() -> None:
    assert _name_of("/autoscaling-api/v1/{project_id}/scaling_group") == (
        "scaling_group"
    )


def test_a_version_segment_after_a_parameter_is_still_skipped() -> None:
    assert _name_of("/{project_id}/v1/servers") == "servers"


def test_the_version_segment_is_found_whatever_its_case_and_minor_number() -> None:
    assert _name_of("/V3.1/{project_id}/tags", "v3.1") == "tags"


def test_without_a_version_segment_the_first_constant_segment_is_used() -> None:
    """The scanner took the version from the file path, not from the URI.

    Nothing is skipped as if it were a version: dropping the first segment
    anyway would leave only `{id}` here, and the endpoint would land in
    `unassigned` instead of `servers`.
    """
    assert _name_of("/servers/{id}", "v2") == "servers"
    assert _name_of("/{project_id}/servers/{id}", "v2") == "servers"


def test_a_segment_the_version_pattern_does_not_match_is_a_constant_segment() -> None:
    """Only the scanner's own version pattern says what a version segment is.

    `v1beta` is not one, so it is the first constant segment of this URI.
    """
    assert _name_of("/v1beta/clusters", "v2") == "v1beta"


def test_the_query_string_is_not_part_of_the_path() -> None:
    assert _name_of("/v2.1/{project_id}/servers?limit={limit}", "v2.1") == "servers"
    assert _name_of("/v2/servers?marker=abc", "v2") == "servers"


def test_a_parameter_whose_name_holds_a_slash_is_one_segment() -> None:
    """A slash inside a placeholder does not split it into a fake constant part.

    `{object/key}` is one parameter: neither `{object` nor `key}` becomes a
    name such as `r__object`.
    """
    assert _name_of("/v1/{bucket}/{object/key}/acl") == "acl"

    grouping = group_endpoints([_endpoint("object", "/v1/{bucket}/{object/key}")])

    assert _resources(grouping, "v1") == {}
    assert _unassigned(grouping, "v1") == [_path("object")]


def test_a_question_mark_inside_a_placeholder_does_not_start_the_query() -> None:
    """Placeholders are found before the query string is cut off.

    The scanner's URI pattern allows a `?` inside a placeholder. Cut at it, this
    URI would keep only `/v1/{filter` and the endpoint would wait in
    `unassigned` instead of joining `servers`.
    """
    assert _name_of("/v1/{filter?x}/servers") == "servers"


@pytest.mark.parametrize(
    "uri",
    [
        "/v1/{}/servers",
        "/v1/project_id}/servers",
    ],
)
def test_a_broken_placeholder_is_skipped_like_a_parameter(uri: str) -> None:
    """A brace never makes a name: `{}` would otherwise become `r___`.

    The scanner reads `{}` as a placeholder; the placeholder pattern does not.
    """
    assert _name_of(uri) == "servers"


def test_percent_encoding_is_undone_segment_by_segment() -> None:
    """An encoded placeholder is a parameter, not the name `r__7bproject_id_7d`."""
    assert _name_of("/v1/%7Bproject_id%7D/servers") == "servers"
    assert _name_of("/v1/%7bproject_id%7d/%7Bid%7D/servers") == "servers"
    assert _name_of("/v1/caf%C3%A9") == "caf_"


def test_an_encoded_question_mark_does_not_end_the_path() -> None:
    assert _name_of("/v1/a%3Fb/{id}") == "a_b"


def test_an_encoded_slash_does_not_split_a_segment() -> None:
    """`os%2Fkeypairs` is one segment as written, not a resource `os`."""
    assert _name_of("/v1/{project_id}/os%2Fkeypairs") == "os_keypairs"


def test_an_encoded_null_is_a_character_not_a_parameter() -> None:
    """`%00` decodes to the stand-in for parameters, but is no parameter.

    The stand-in is looked for before a segment is decoded, so `a%00b` still
    names the resource.
    """
    assert _name_of("/v1/a%00b/servers") == "a_b"


def test_a_further_version_segment_is_skipped_too() -> None:
    """`v2` here is a version, not a resource: skipped like the first one."""
    assert _name_of("/v1/{project_id}/v2/servers") == "servers"
    assert _name_of("/v1/{project_id}/V2.1/servers") == "servers"


def test_a_version_segment_at_the_end_of_the_uri_leaves_no_segment() -> None:
    """The scanner read `v1` from this URI's last segment, so nothing follows it.

    The constant segment before the version is not the resource (ADR-0057); the
    endpoint waits in `unassigned` for the user to place it.
    """
    grouping = group_endpoints([_endpoint("versioned", "/servers/v1")])

    assert _resources(grouping, "v1") == {}
    assert _unassigned(grouping, "v1") == [_path("versioned")]


def test_a_query_string_right_after_the_version_leaves_no_segment() -> None:
    grouping = group_endpoints([_endpoint("versions", "/v1?details=true")])

    assert _resources(grouping, "v1") == {}
    assert _unassigned(grouping, "v1") == [_path("versions")]


# ---------------------------------------------------------------------------
# What the rule cannot place
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "/v1/{project_id}",
        "/v1/{project_id}/{server_id}",
        "/v1/",
        "/v1",
        "/v1/{project_id}/{name}.json",
    ],
)
def test_no_constant_segment_after_the_version_is_unassigned(uri: str) -> None:
    grouping = group_endpoints([_endpoint("root", uri)])

    assert _resources(grouping, "v1") == {}
    assert _unassigned(grouping, "v1") == [_path("root")]


def test_an_endpoint_without_a_version_is_in_no_version_even_with_a_segment() -> None:
    grouping = group_endpoints(
        [
            _endpoint("list", "/servers", api_version=None),
            _endpoint("show", "/v1/servers/{id}", api_version=None),
        ]
    )

    assert grouping.no_version == [_path("list"), _path("show")]
    assert grouping.versions == []


def test_an_empty_version_is_no_version_rather_than_a_nameless_group() -> None:
    grouping = group_endpoints([_endpoint("blank", "/v1/servers", api_version="")])

    assert grouping.no_version == [_path("blank")]
    assert grouping.versions == []


def test_endpoints_are_grouped_whatever_their_status() -> None:
    """ADR-0058: a broken endpoint is in the editor too, for the user to place."""
    broken = SectionScanResult(
        status=SectionStatus.FAILED,
        issues=[Issue(code=IssueCode.MALFORMED_GRID_TABLE)],
    )
    endpoint = _endpoint("broken", "/v1/servers/{id}", body=broken)
    assert analyze_document(endpoint).overall_status is not OverallStatus.OK

    grouping = group_endpoints([_endpoint("ok", "/v1/servers"), endpoint])

    assert _resources(grouping, "v1") == {"servers": [_path("broken"), _path("ok")]}


# ---------------------------------------------------------------------------
# Resource names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("segment", "name"),
    [
        ("Servers", "servers"),
        ("os-keypairs", "os_keypairs"),
        ("servers.json", "servers_json"),
        ("a--b", "a__b"),
        ("snake_case_2", "snake_case_2"),
        ("café", "caf_"),
        ("2fa", "r_2fa"),
        ("_private", "r__private"),
        ("-x", "r__x"),
    ],
)
def test_a_segment_is_normalized_into_a_valid_name(segment: str, name: str) -> None:
    """Lower case, invalid characters to `_`, `r_` before a non-letter - no more."""
    assert _name_of(f"/v1/{{project_id}}/{segment}") == name
    assert re.fullmatch(RESOURCE_NAME_PATTERN, name)


def test_segments_that_normalize_to_one_name_share_a_resource() -> None:
    grouping = group_endpoints(
        [
            _endpoint("dash", "/v2/os-keypairs", api_version="v2"),
            _endpoint("underscore", "/v2/os_keypairs/{name}", api_version="v2"),
            _endpoint("upper", "/v2/OS-Keypairs/{name}/detail", api_version="v2"),
        ],
    )

    assert _resources(grouping, "v2") == {
        "os_keypairs": [_path("dash"), _path("underscore"), _path("upper")]
    }


def test_the_same_name_in_two_versions_is_two_resources() -> None:
    grouping = group_endpoints(
        [
            _endpoint("v1-list", "/v1/{project_id}/servers"),
            _endpoint("v2-list", "/v2/{project_id}/servers", api_version="v2"),
        ]
    )

    assert _resources(grouping, "v1") == {"servers": [_path("v1-list")]}
    assert _resources(grouping, "v2") == {"servers": [_path("v2-list")]}


# ---------------------------------------------------------------------------
# The whole result
# ---------------------------------------------------------------------------


def test_every_endpoint_is_placed_exactly_once() -> None:
    endpoints = [
        _endpoint("servers", "/v1/{project_id}/servers"),
        _endpoint("server", "/v1/{project_id}/servers/{id}"),
        _endpoint("flavors", "/v1/{project_id}/flavors"),
        _endpoint("root", "/v1/{project_id}"),
        _endpoint("v2", "/v2/{project_id}/servers", api_version="v2"),
        _endpoint("bare", "/servers", api_version=None),
    ]

    grouping = group_endpoints(endpoints)

    placed = [
        *grouping.no_version,
        *(
            path
            for group in grouping.versions
            for path in [
                *group.unassigned,
                *(p for r in group.resources for p in r.endpoints),
            ]
        ),
    ]
    assert sorted(placed) == sorted(e.path for e in endpoints)
    assert [g.api_version for g in grouping.versions] == ["v1", "v2"]
    assert _resources(grouping, "v1") == {
        "flavors": [_path("flavors")],
        "servers": [_path("server"), _path("servers")],
    }
    assert _unassigned(grouping, "v1") == [_path("root")]
    assert grouping.no_version == [_path("bare")]


def test_versions_are_ordered_by_number_not_by_text() -> None:
    grouping = group_endpoints(
        [
            _endpoint(version, f"/{version}/servers", api_version=version)
            for version in ["v10", "v2.1", "v1", "v2", "v2.10"]
        ]
    )

    assert [g.api_version for g in grouping.versions] == [
        "v1",
        "v2",
        "v2.1",
        "v2.10",
        "v10",
    ]


def test_the_result_does_not_depend_on_the_order_the_endpoints_came_in() -> None:
    endpoints = [
        _endpoint("g", "/v10/{project_id}/zones", api_version="v10"),
        _endpoint("b", "/v2/{project_id}/zones", api_version="v2"),
        _endpoint("a", "/v1/{project_id}/servers"),
        _endpoint("c", "/v1/{project_id}"),
        _endpoint("d", "/v1/{project_id}/flavors"),
        _endpoint("e", "/zones", api_version=None),
        _endpoint("f", "/v1/{project_id}/servers/{id}"),
        _endpoint("h", "/v1/{project_id}/{id}"),
        _endpoint("i", "/flavors", api_version=None),
    ]

    grouping = group_endpoints(endpoints)

    assert grouping == group_endpoints(endpoints[::-1])
    # two items in every list, so each list's order is actually tested; a dict
    # compares without order, hence the names as a list
    [v1] = [group for group in grouping.versions if group.api_version == "v1"]
    assert [resource.name for resource in v1.resources] == ["flavors", "servers"]
    assert _resources(grouping, "v1")["servers"] == [_path("a"), _path("f")]
    assert _unassigned(grouping, "v1") == [_path("c"), _path("h")]
    assert grouping.no_version == [_path("e"), _path("i")]


def test_document_rows_are_grouped_from_their_projected_columns() -> None:
    """The caller need not deserialize payloads: the projected columns suffice.

    The rows carry no payload at all. A row's URI is nullable; without one there
    is no segment, so the endpoint is unassigned rather than dropped.
    """
    rows = [
        _row("list", "/v1/{project_id}/servers", "v1"),
        _row("no-uri", None, "v1"),
        _row("bare", "/servers", None),
    ]

    grouping = group_endpoints(rows)

    assert _resources(grouping, "v1") == {"servers": [_path("list")]}
    assert _unassigned(grouping, "v1") == [_path("no-uri")]
    assert grouping.no_version == [_path("bare")]


def test_a_document_that_is_not_an_endpoint_is_refused() -> None:
    """A caller that forgot to filter by kind fails instead of filling the lists.

    A page has no version and no URI, so it would land in "no version" and be
    shown there as an endpoint.
    """
    page = _row("overview", None, None, kind=Document.model_fields["kind"].default)

    with pytest.raises(NotAnEndpointError, match="not an endpoint") as refused:
        group_endpoints([_row("list", "/v1/servers", "v1"), page])

    # a caller error: `except ValueError` around the call - which catches the
    # ValidationError of a broken grouping invariant - does not swallow it
    assert not isinstance(refused.value, ValueError)


def test_no_endpoints_give_an_empty_grouping() -> None:
    assert group_endpoints([]) == EndpointGrouping()


def test_one_path_given_twice_is_refused_rather_than_placed_twice() -> None:
    with pytest.raises(ValidationError, match="exactly once"):
        group_endpoints(
            [
                _endpoint("same", "/v1/servers"),
                _endpoint("same", "/v1/{project_id}"),
            ]
        )


# ---------------------------------------------------------------------------
# The models refuse what the rule may not produce
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Servers", "os-keypairs", "2fa", "_x", ""])
def test_a_resource_name_outside_the_pattern_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        GroupedResource(name=name, endpoints=[_path("one")])


def test_a_resource_without_endpoints_is_refused() -> None:
    with pytest.raises(ValidationError):
        GroupedResource(name="servers", endpoints=[])


def test_two_resources_of_one_name_in_one_version_are_refused() -> None:
    with pytest.raises(ValidationError, match="unique"):
        VersionGroup(
            api_version="v1",
            resources=[
                GroupedResource(name="servers", endpoints=[_path("a")]),
                GroupedResource(name="servers", endpoints=[_path("b")]),
            ],
        )


def test_a_version_group_without_a_version_is_refused() -> None:
    with pytest.raises(ValidationError):
        VersionGroup(api_version="", unassigned=[_path("a")])


def test_a_version_group_without_endpoints_is_refused() -> None:
    with pytest.raises(ValidationError, match="holds no endpoint"):
        VersionGroup(api_version="v1")


def test_one_version_grouped_twice_is_refused() -> None:
    with pytest.raises(ValidationError, match="grouped once"):
        EndpointGrouping(
            versions=[
                VersionGroup(api_version="v1", unassigned=[_path("a")]),
                VersionGroup(api_version="v1", unassigned=[_path("b")]),
            ]
        )


def test_an_endpoint_in_a_resource_and_in_unassigned_is_refused() -> None:
    with pytest.raises(ValidationError, match="exactly once"):
        EndpointGrouping(
            versions=[
                VersionGroup(
                    api_version="v1",
                    resources=[GroupedResource(name="servers", endpoints=[_path("a")])],
                    unassigned=[_path("a")],
                )
            ]
        )


def test_an_endpoint_in_two_versions_is_refused() -> None:
    with pytest.raises(ValidationError, match="exactly once"):
        EndpointGrouping(
            versions=[
                VersionGroup(api_version="v1", unassigned=[_path("a")]),
                VersionGroup(api_version="v2", unassigned=[_path("a")]),
            ],
            no_version=[],
        )


def test_an_endpoint_in_no_version_and_in_a_version_is_refused() -> None:
    with pytest.raises(ValidationError, match="exactly once"):
        EndpointGrouping(
            versions=[VersionGroup(api_version="v1", unassigned=[_path("a")])],
            no_version=[_path("a")],
        )
