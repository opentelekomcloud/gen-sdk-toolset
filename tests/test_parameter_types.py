import pytest
from docutils import nodes
from docutils.core import publish_doctree

from tools.scanner.parsers.docutils.field_type import (
    classify_type,
    extract_struct_type_name,
)
from tools.scanner.parsers.docutils.table import extract_parameter_table
from tools.shared.ir import ParameterType
from tools.shared.scan import IssueCode


def test_legacy_otc_parameter_types() -> None:
    doctree = publish_doctree(
        """
=================== =================== ===========
Name                Type                Description
=================== =================== ===========
configuration       Data structure      Settings
items               List data structure Nested items
gateway              Dictionary          Nested gateway
gateways             List                Gateway list
period_start_date   Long integer        Start time
=================== =================== ===========
"""
    )
    table = next(iter(doctree.findall(nodes.table)))

    extraction = extract_parameter_table(table)

    assert [parameter.param_type for parameter in extraction.parameters] == [
        ParameterType.OBJECT,
        ParameterType.ARRAY,
        ParameterType.OBJECT,
        ParameterType.ARRAY,
        ParameterType.LONG,
    ]
    assert [parameter.type_name for parameter in extraction.parameters] == [
        None,
        None,
        None,
        None,
        None,
    ]
    assert extraction.metrics.fields_recognized == 5
    assert extraction.metrics.fields_unknown_type == 0


# --------------------------------------------------------------------------- #
# Type aliases
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "written,expected",
    [
        ("int", ParameterType.INTEGER),
        ("int32", ParameterType.INTEGER),
        ("Number", ParameterType.INTEGER),
        ("int64", ParameterType.LONG),
        ("dict", ParameterType.OBJECT),
        ("json", ParameterType.OBJECT),
        ("map", ParameterType.OBJECT),
        ("jsonarray", ParameterType.ARRAY),
        ("date", ParameterType.STRING),
        ("timestamp", ParameterType.STRING),
    ],
)
def test_supported_aliases_normalize_to_a_canonical_type(written, expected) -> None:
    assert classify_type(written) == expected


@pytest.mark.parametrize(
    "written,expected",
    [
        ("INT", ParameterType.INTEGER),
        ("Int64", ParameterType.LONG),
        ("JSONArray", ParameterType.ARRAY),
        ("TimeStamp", ParameterType.STRING),
        ("  Dict  ", ParameterType.OBJECT),
    ],
)
def test_aliases_are_matched_regardless_of_case_or_padding(written, expected) -> None:
    """Whichever way a page writes it, the type is the same type - documentation
    is written by people, and case is not information."""
    assert classify_type(written) == expected


@pytest.mark.parametrize(
    "written,expected",
    [
        ("String", ParameterType.STRING),
        ("Integer", ParameterType.INTEGER),
        ("Long", ParameterType.LONG),
        ("Boolean", ParameterType.BOOLEAN),
        ("Object", ParameterType.OBJECT),
        ("Array", ParameterType.ARRAY),
        ("Array of strings", ParameterType.ARRAY_OF_STRINGS),
        ("Array of objects", ParameterType.ARRAY_OF_OBJECTS),
        ("Dictionary", ParameterType.OBJECT),
        ("Data structure", ParameterType.OBJECT),
        ("List", ParameterType.ARRAY),
        ("List data structure", ParameterType.ARRAY),
        ("Long integer", ParameterType.LONG),
    ],
)
def test_canonical_and_legacy_types_are_unchanged(written, expected) -> None:
    """The aliases are additions. Everything the parser read before it still
    reads the same way, which is what makes this change safe to apply to
    snapshots already stored."""
    assert classify_type(written) == expected


@pytest.mark.parametrize("written", ["Interger", "Sting", "Boolena", "objekt", "in32"])
def test_a_misspelling_is_still_unknown(written) -> None:
    """The aliases are documentation conventions, not spelling correction.
    Absorbing a typo would turn a defect the panel is meant to count into a
    parameter that looks read - and the count is the product."""
    assert classify_type(written) == ParameterType.UNKNOWN


@pytest.mark.parametrize("written", ["creation date", "date of birth", "int values"])
def test_an_alias_inside_prose_is_not_a_type(written) -> None:
    """Whole-cell matching only: a description mentioning a type is not a type
    declaration, and typing a column from its wording would invent data."""
    assert classify_type(written) == ParameterType.UNKNOWN


def test_aliases_are_recognized_in_a_real_table() -> None:
    """End to end through the table parser: an aliased type counts as read, and
    raises no diagnostic."""
    doctree = publish_doctree(
        """
=================== =================== ===========
Name                Type                Description
=================== =================== ===========
port                int32               Listening port
size                int64               Volume size
tags                dict                Free-form tags
addresses           jsonarray           Bound addresses
created_at          timestamp           Creation time
=================== =================== ===========
"""
    )
    table = next(iter(doctree.findall(nodes.table)))

    extraction = extract_parameter_table(table)

    assert [parameter.param_type for parameter in extraction.parameters] == [
        ParameterType.INTEGER,
        ParameterType.LONG,
        ParameterType.OBJECT,
        ParameterType.ARRAY,
        ParameterType.STRING,
    ]
    # An alias names the type itself. `type_name` is for a struct the cell
    # *refers* to, so `dict` must not come back as a reference to "dict".
    assert [parameter.type_name for parameter in extraction.parameters] == [None] * 5
    assert extraction.metrics.fields_recognized == 5
    assert extraction.metrics.fields_unknown_type == 0
    assert extraction.issues == []


def test_a_misspelled_type_still_raises_its_diagnostic() -> None:
    """The other half of the same guarantee: what the aliases do not cover is
    still counted and still named, with the text that was not understood."""
    doctree = publish_doctree(
        """
=================== =================== ===========
Name                Type                Description
=================== =================== ===========
count               Interger            How many
=================== =================== ===========
"""
    )
    table = next(iter(doctree.findall(nodes.table)))

    extraction = extract_parameter_table(table)

    assert extraction.parameters[0].param_type is ParameterType.UNKNOWN
    assert extraction.metrics.fields_unknown_type == 1
    assert extraction.metrics.fields_recognized == 0
    (issue,) = extraction.issues
    assert issue.code is IssueCode.UNKNOWN_TYPE_FORMAT
    assert "Interger" in issue.details


@pytest.mark.parametrize("written", ["dict", "json", "map", "jsonarray", "Dictionary"])
def test_a_mapping_alias_references_no_struct(written) -> None:
    """The mapping aliases classify as object or array, which is what makes the
    parser look for a referenced structure name. There is none: the cell is the
    type, and reporting one would invent a reference the page never wrote."""
    assert extract_struct_type_name(written) is None


@pytest.mark.parametrize(
    "written,expected",
    [("ExternalIp object", "ExternalIp"), ("Array of ExternalIp", "ExternalIp")],
)
def test_a_real_struct_reference_is_still_extracted(written, expected) -> None:
    assert extract_struct_type_name(written) == expected
