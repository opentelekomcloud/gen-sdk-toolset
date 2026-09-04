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
        ("Array of ExternalIp", ParameterType.ARRAY_OF_OBJECTS),
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


# --------------------------------------------------------------------------- #
# Named container and structure syntax
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "written,expected",
    [
        ("List<Node>", ParameterType.ARRAY_OF_OBJECTS),
        ("Map<String, Node>", ParameterType.OBJECT),
        ("Schedule data structure", ParameterType.OBJECT),
        ("Node structure array", ParameterType.ARRAY_OF_OBJECTS),
    ],
)
def test_named_syntax_normalizes_to_a_canonical_type(written, expected) -> None:
    """The four named forms carry a structure name where the prose forms carry
    the word `object`. They mean the same thing and land on the same values -
    the IR grows no `List` and no `Map`."""
    assert classify_type(written) == expected


@pytest.mark.parametrize(
    "written,expected",
    [
        ("List<Node>", "Node"),
        ("Schedule data structure", "Schedule"),
        ("Node structure array", "Node"),
    ],
)
def test_named_syntax_preserves_the_structure_name(written, expected) -> None:
    """The name is the whole point of these forms: it is what a nested table is
    later matched against, so dropping it would lose the reference."""
    assert extract_struct_type_name(written) == expected


def test_a_map_references_no_structure() -> None:
    """`Map<K, V>` names its key and value types rather than a structure, and
    the IR has no map type to keep them in. It reads as a plain object, and
    returning `String` or `Node` here would invent a reference the cell never
    made."""
    assert extract_struct_type_name("Map<String, Node>") is None


@pytest.mark.parametrize(
    "written,expected",
    [
        ("list<node>", ParameterType.ARRAY_OF_OBJECTS),
        ("MAP<String,Node>", ParameterType.OBJECT),
        ("LIST < Node >", ParameterType.ARRAY_OF_OBJECTS),
        ("Schedule   data structure", ParameterType.OBJECT),
        ("  Node structure array  ", ParameterType.ARRAY_OF_OBJECTS),
    ],
)
def test_named_syntax_survives_case_and_spacing(written, expected) -> None:
    assert classify_type(written) == expected


def test_the_structure_name_keeps_the_spelling_the_page_used() -> None:
    """Matching ignores case; the captured name does not. It has to match a
    nested table's heading, which is written the way the author wrote it."""
    assert extract_struct_type_name("LIST < CreateFirewallOption >") == (
        "CreateFirewallOption"
    )


@pytest.mark.parametrize(
    "written,expected",
    [
        ("List<String>", ParameterType.ARRAY_OF_STRINGS),
        ("List<Integer>", ParameterType.ARRAY_OF_INTEGERS),
    ],
)
def test_a_list_of_primitives_reads_as_the_composite_it_is(written, expected) -> None:
    """`List<String>` is `Array of strings` written another way, and reads as
    one. Calling it an object array would leave a `type_name` of "String"
    behind - a reference to a structure that does not exist and never will."""
    assert classify_type(written) == expected


@pytest.mark.parametrize(
    "written,expected_name",
    [
        # The inner form is normalized before the outer one, so the element is
        # an object - not a structure named `Map<String, Node>`.
        ("List<Map<String, Node>>", None),
        # Nested lists flatten, and the structure at the bottom is still named.
        ("List<List<Node>>", "Node"),
        # `Set` is a container this module does not know. The cell is still an
        # array, but `Set<Node>` is not a name anything could resolve, so none
        # is reported rather than one being invented.
        ("List<Set<Node>>", None),
        # An element of nothing at all: still an array, still no name.
        ("List<   >", None),
    ],
)
def test_a_nested_generic_invents_no_structure_name(written, expected_name) -> None:
    assert classify_type(written) == ParameterType.ARRAY_OF_OBJECTS
    assert extract_struct_type_name(written) == expected_name


@pytest.mark.parametrize(
    "written,expected",
    [
        ("List", ParameterType.ARRAY),
        ("List data structure", ParameterType.ARRAY),
        ("Dictionary", ParameterType.OBJECT),
        ("Data structure", ParameterType.OBJECT),
    ],
)
def test_the_bare_legacy_forms_still_mean_what_they_meant(written, expected) -> None:
    """`List data structure` names no structure - it is the legacy spelling of
    an array. It is matched before the named forms, or it would come back as an
    array of a structure called "List"."""
    assert classify_type(written) == expected
    assert extract_struct_type_name(written) is None


@pytest.mark.parametrize(
    "written,expected",
    [
        ("Node\nstructure array", ParameterType.ARRAY_OF_OBJECTS),
        ("List<\nNode>", ParameterType.ARRAY_OF_OBJECTS),
    ],
)
def test_a_wrapped_cell_reads_the_same_as_a_single_line(written, expected) -> None:
    """A narrow Type column wraps, and docutils keeps the newline. The cell says
    the same thing either way."""
    assert classify_type(written) == expected
    assert extract_struct_type_name(written) == "Node"


@pytest.mark.parametrize(
    "written,expected",
    [
        # `List` and `String` are types, so neither cell names a structure.
        # Rewriting the first would turn an array into an object.
        ("List data structure", ParameterType.ARRAY),
        ("String data structure", ParameterType.STRING),
        # The same cell wrapped: no longer an exact alias, and still not a
        # structure called "List".
        ("List  data structure", ParameterType.UNKNOWN),
        ("List\ndata structure", ParameterType.UNKNOWN),
    ],
)
def test_a_name_that_is_already_a_type_names_no_structure(written, expected) -> None:
    """These read exactly as they read before the named forms existed. The last
    two stay `Unknown` and are counted - which is the honest answer, and a far
    better one than a confident `Object` referring to a structure named "List".

    Only the type is asserted: whether a cell carries a struct name is a
    question the parser asks of `STRUCT_TYPES` alone, and it is pinned for the
    array case in `test_the_bare_legacy_forms_still_mean_what_they_meant`."""
    assert classify_type(written) == expected


@pytest.mark.parametrize(
    "written",
    [
        "Specifies the schedule data structure",
        "See the Node structure array",
        "the request body data structure",
    ],
)
def test_prose_ending_in_a_container_word_is_not_a_structure(written) -> None:
    """A structure name is one identifier. A sentence that happens to end in
    "data structure" is a description, and naming a structure after it would
    invent a reference no page ever made - the same rule that keeps "creation
    date" from being typed as a date."""
    assert classify_type(written) == ParameterType.UNKNOWN


@pytest.mark.parametrize(
    "written",
    ["Node structures", "structure array", "data structure of Node", "List<>"],
)
def test_a_near_miss_is_still_unknown(written) -> None:
    """Only the four documented forms are read. Anything adjacent to them is
    reported rather than guessed at, which is what keeps `UNKNOWN_TYPE_FORMAT` a
    measurement instead of a rounding error."""
    assert classify_type(written) == ParameterType.UNKNOWN


def test_named_syntax_is_recognized_in_a_real_table() -> None:
    """End to end through the table parser: each form counts as read, keeps its
    structure name, and raises no diagnostic."""
    doctree = publish_doctree(
        """
=================== ======================== ===========
Name                Type                     Description
=================== ======================== ===========
nodes               List<Node>               Cluster nodes
labels              Map<String, String>      Free-form labels
schedule            Schedule data structure  Rotation window
addresses           Node structure array     Bound addresses
=================== ======================== ===========
"""
    )
    table = next(iter(doctree.findall(nodes.table)))

    extraction = extract_parameter_table(table)

    assert [parameter.param_type for parameter in extraction.parameters] == [
        ParameterType.ARRAY_OF_OBJECTS,
        ParameterType.OBJECT,
        ParameterType.OBJECT,
        ParameterType.ARRAY_OF_OBJECTS,
    ]
    assert [parameter.type_name for parameter in extraction.parameters] == [
        "Node",
        None,
        "Schedule",
        "Node",
    ]
    assert extraction.metrics.fields_recognized == 4
    assert extraction.metrics.fields_unknown_type == 0
    assert extraction.issues == []


# --------------------------------------------------------------------------- #
# Structure names the parser keeps
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "written,expected",
    [
        ("Array of RequestTag objects", "RequestTag"),
        ("CreateFirewallOption object", "CreateFirewallOption"),
        ("Array of ExternalIp", "ExternalIp"),
        # Names of their own that happen to end in `s`. The plural is only ever
        # tried to recognise a type, so a real name keeps it.
        ("Array of Tags objects", "Tags"),
        ("Options object", "Options"),
        ("Address structure array", "Address"),
    ],
)
def test_a_real_structure_name_survives(written, expected) -> None:
    assert extract_struct_type_name(written) == expected
