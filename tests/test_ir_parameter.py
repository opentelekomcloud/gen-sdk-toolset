"""S3 (#6): `Parameter.type_name` field + nested-resolution issue codes.

Pure-domain guards: the new optional `type_name` field defaults to ``None``
and round-trips through JSON, and the five issue codes the resolver (S5) and
wire-in (S6) rely on exist with stable values.
"""

from __future__ import annotations

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
    assert IssueCode.NESTED_TABLE_EMPTY.value == "nested_table_empty"
    assert IssueCode.NESTED_CIRCULAR_REF.value == "nested_circular_ref"
    assert IssueCode.NESTED_REF_NOT_A_TABLE.value == "nested_ref_not_a_table"
    assert IssueCode.NESTED_REF_EXTERNAL.value == "nested_ref_external"
