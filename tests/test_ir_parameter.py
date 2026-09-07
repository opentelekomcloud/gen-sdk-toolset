"""S3 (#6): `Parameter.type_name` field + nested-resolution issue codes.

Pure-domain guards: the new optional `type_name` field defaults to ``None``
and round-trips through JSON, and the five issue codes the resolver (S5) and
wire-in (S6) rely on exist with stable values.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.shared.ir import Parameter, ParameterType
from tools.shared.scan import IssueCode


def test_type_name_defaults_to_none() -> None:
    param = Parameter(name="firewall")
    assert param.type_name is None


def test_type_name_serializes() -> None:
    param = Parameter(
        name="firewall",
        param_type=ParameterType.OBJECT,
        type_name="CreateFirewallOption",
    )
    dumped = param.model_dump(mode="json")
    assert dumped["type_name"] == "CreateFirewallOption"
    assert Parameter.model_validate(dumped) == param


def test_type_name_none_round_trips() -> None:
    param = Parameter(name="name", param_type=ParameterType.STRING)
    dumped = param.model_dump(mode="json")
    assert dumped["type_name"] is None
    assert Parameter.model_validate(dumped) == param


def test_nested_issue_codes_exist() -> None:
    assert IssueCode.NESTED_TABLE_NOT_FOUND.value == "nested_table_not_found"
    assert IssueCode.NESTED_PARENT_NOT_FOUND.value == "nested_parent_not_found"
    assert IssueCode.PATH_PARAMETER_NOT_IN_URI.value == "path_parameter_not_in_uri"
    assert IssueCode.NESTED_TABLE_EMPTY.value == "nested_table_empty"
    assert IssueCode.NESTED_CIRCULAR_REF.value == "nested_circular_ref"
    assert IssueCode.NESTED_REF_NOT_A_TABLE.value == "nested_ref_not_a_table"
    assert IssueCode.NESTED_REF_EXTERNAL.value == "nested_ref_external"


# --------------------------------------------------------------------------- #
# Reading a schema-v1 payload
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "stored,param_type,element_type",
    [
        ("Array of strings", ParameterType.ARRAY, ParameterType.STRING),
        ("Array of integers", ParameterType.ARRAY, ParameterType.INTEGER),
        ("Array of objects", ParameterType.ARRAY, ParameterType.OBJECT),
    ],
)
def test_a_v1_composite_loads_as_the_pair_it_stood_for(
    stored, param_type, element_type
) -> None:
    """Snapshots written before this change spelled the array and its element
    as one value. They are still read, and mean what they meant - otherwise
    every stored parameter would come back `Unknown` and the panel's numbers
    would move without a rescan."""
    parameter = Parameter.model_validate({"name": "tags", "param_type": stored})

    assert parameter.param_type is param_type
    assert parameter.element_type is element_type


def test_a_v1_composite_survives_nested_in_a_document() -> None:
    """The split runs wherever a Parameter is built, children included."""
    parameter = Parameter.model_validate(
        {
            "name": "server",
            "param_type": "Object",
            "children": [{"name": "tags", "param_type": "Array of strings"}],
        }
    )

    child = parameter.children[0]
    assert child.param_type is ParameterType.ARRAY
    assert child.element_type is ParameterType.STRING


def test_a_v2_payload_round_trips_unchanged() -> None:
    parameter = Parameter(
        name="tags",
        param_type=ParameterType.ARRAY,
        element_type=ParameterType.BOOLEAN,
    )

    restored = Parameter.model_validate(parameter.model_dump(mode="json"))

    assert restored == parameter


def test_a_v1_payload_that_names_no_composite_is_untouched() -> None:
    parameter = Parameter.model_validate({"name": "id", "param_type": "String"})

    assert parameter.param_type is ParameterType.STRING
    assert parameter.element_type is None


def test_validating_an_existing_parameter_is_a_no_op() -> None:
    """`model_validate` is handed a model, not a payload, when a caller passes
    a `Parameter` where one is expected. The v1 split only applies to stored
    payloads, so it has to let anything that is not a mapping straight through."""
    parameter = Parameter(
        name="tags",
        param_type=ParameterType.ARRAY,
        element_type=ParameterType.BOOLEAN,
    )

    assert Parameter.model_validate(parameter) == parameter


def test_a_non_mapping_input_passes_through_the_v1_split() -> None:
    """`model_validate` also accepts an object with `from_attributes`, and the
    split reads a stored payload's keys. It has to let anything that is not a
    mapping straight through rather than assume `.get` exists on it."""
    row = SimpleNamespace(name="tags", param_type="Array", element_type="Boolean")

    parameter = Parameter.model_validate(row, from_attributes=True)

    assert parameter.param_type is ParameterType.ARRAY
    assert parameter.element_type is ParameterType.BOOLEAN
