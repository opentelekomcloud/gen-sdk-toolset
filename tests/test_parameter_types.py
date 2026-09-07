import pytest
from docutils import nodes
from docutils.core import publish_doctree

from tools.scanner.parsers.docutils.field_type import (
    classify_type,
    extract_struct_type_name,
    parse_field_type,
)
from tools.scanner.parsers.docutils.table import extract_parameter_table
from tools.shared.ir import Parameter, ParameterType
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
        ("Array of strings", ParameterType.ARRAY),
        ("Array of objects", ParameterType.ARRAY),
        ("Array of ExternalIp", ParameterType.ARRAY),
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
    "written,param_type,element_type",
    [
        ("List<Node>", ParameterType.ARRAY, ParameterType.OBJECT),
        ("Map<String, Node>", ParameterType.OBJECT, None),
        ("Schedule data structure", ParameterType.OBJECT, None),
        ("Node structure array", ParameterType.ARRAY, ParameterType.OBJECT),
    ],
)
def test_named_syntax_normalizes_to_a_canonical_type(
    written, param_type, element_type
) -> None:
    """The four named forms carry a structure name where the prose forms carry
    the word `object`. They mean the same thing and land on the same values -
    the IR grows no `List` and no `Map`."""
    field = parse_field_type(written)
    assert (field.param_type, field.element_type) == (param_type, element_type)


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
        ("list<node>", ParameterType.ARRAY),
        ("MAP<String,Node>", ParameterType.OBJECT),
        ("LIST < Node >", ParameterType.ARRAY),
        ("Schedule   data structure", ParameterType.OBJECT),
        ("  Node structure array  ", ParameterType.ARRAY),
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
    "written,element_type",
    [
        ("List<String>", ParameterType.STRING),
        ("List<Integer>", ParameterType.INTEGER),
        ("List<Boolean>", ParameterType.BOOLEAN),
        ("List<Long>", ParameterType.LONG),
        ("List<Float>", ParameterType.FLOAT),
        ("List<Double>", ParameterType.DOUBLE),
    ],
)
def test_a_list_of_primitives_records_what_it_holds(written, element_type) -> None:
    """`List<String>` is `Array of strings` written another way. Every one of
    these is expressible now: under the old composite types only strings,
    integers and objects had a member, so booleans and longs were filed as
    object arrays and left a `type_name` naming a structure nobody wrote."""
    field = parse_field_type(written)
    assert field.param_type is ParameterType.ARRAY
    assert field.element_type is element_type
    assert field.type_name is None


@pytest.mark.parametrize(
    "written",
    [
        # No type argument at all.
        "List<>",
        "List<   >",
        "List< >",
        # A map needs a key and a value; one argument is not a map.
        "Map<Node>",
        "Map<String>",
        "Map<>",
        # Unbalanced, or no brackets to speak of.
        "List<Node>>",
        "List>",
        "List<",
        "Map<String, Node>>",
        "<Node>",
        # Punctuation where a type argument belongs.
        "List<,>",
        "Map<,>",
        # More arguments than the form has places for.
        "List<Node,Node>",
        "Map<String, Node, Extra>",
        # Nested generics: an array of maps has no representation here that
        # would not be a guess about which of the two the row meant.
        "List<Map<String, Node>>",
        "List<List<Node>>",
        # A container this module does not know.
        "List<Set<Node>>",
    ],
)
def test_generic_syntax_that_cannot_be_read_stays_unknown(written) -> None:
    """Angle brackets say the author wrote generic syntax. If it is not one of
    the two forms we read, falling back to prose matching would find `String`
    inside `List<Map<String, Node>>` and call the row a string. `Unknown` is
    the true answer, and it is the one that gets counted."""
    field = parse_field_type(written)
    assert field.param_type is ParameterType.UNKNOWN
    assert field.element_type is None
    assert field.type_name is None


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
        ("Node\nstructure array", ParameterType.ARRAY),
        ("List<\nNode>", ParameterType.ARRAY),
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
        ParameterType.ARRAY,
        ParameterType.OBJECT,
        ParameterType.OBJECT,
        ParameterType.ARRAY,
    ]
    assert [parameter.element_type for parameter in extraction.parameters] == [
        ParameterType.OBJECT,
        None,
        None,
        ParameterType.OBJECT,
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


# --------------------------------------------------------------------------- #
# What an array holds
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "written,element_type",
    [
        ("Array of strings", ParameterType.STRING),
        ("Array of integers", ParameterType.INTEGER),
        ("Array of objects", ParameterType.OBJECT),
        # None of these three had a composite type to land on before, so each
        # was filed as an object array - and left its element word behind in
        # `type_name`, naming a structure no page ever wrote.
        ("Array of booleans", ParameterType.BOOLEAN),
        ("Array of longs", ParameterType.LONG),
        ("Array of floats", ParameterType.FLOAT),
        ("Array of doubles", ParameterType.DOUBLE),
        # Singular, which the documentation also writes.
        ("Array of string", ParameterType.STRING),
        ("Array of boolean", ParameterType.BOOLEAN),
    ],
)
def test_an_array_records_the_primitive_it_holds(written, element_type) -> None:
    field = parse_field_type(written)

    assert field.param_type is ParameterType.ARRAY
    assert field.element_type is element_type
    assert field.type_name is None, "a primitive array references no structure"


def test_a_bare_array_says_nothing_about_its_elements() -> None:
    """`None` is not `Object`. The page did not say what the array holds, and
    recording `Object` would be us saying it instead."""
    field = parse_field_type("Array")

    assert field.param_type is ParameterType.ARRAY
    assert field.element_type is None
    assert field.type_name is None


@pytest.mark.parametrize(
    "written,type_name",
    [
        ("Array of Node objects", "Node"),
        ("Array of RequestTag objects", "RequestTag"),
        ("Array of ExternalIp", "ExternalIp"),
        ("Node structure array", "Node"),
        ("List<Node>", "Node"),
    ],
)
def test_an_array_of_structures_keeps_the_element_and_the_name(
    written, type_name
) -> None:
    """Both facts, not one: `Object` says a generator must build a type, and
    the name says which documented table defines it."""
    field = parse_field_type(written)

    assert field.param_type is ParameterType.ARRAY
    assert field.element_type is ParameterType.OBJECT
    assert field.type_name == type_name


@pytest.mark.parametrize(
    "written,supports",
    [
        # An object always can.
        ("Object", True),
        ("Schedule data structure", True),
        # An array of structures can; an array of primitives cannot.
        ("Array of Node objects", True),
        ("List<Node>", True),
        ("Array of strings", False),
        ("Array of booleans", False),
        ("List<Boolean>", False),
        # An array whose elements the page never named might, and a nested
        # table naming it is the evidence that decides.
        ("Array", True),
        ("List", True),
        # Primitives never do.
        ("String", False),
        ("Interger", False),
    ],
)
def test_whether_a_cell_could_hold_a_nested_table(written, supports) -> None:
    """`ParameterType.ARRAY` alone cannot answer this any more, which is why
    the question moved to `Parameter`."""
    field = parse_field_type(written)
    parameter = Parameter(
        name="x",
        param_type=field.param_type,
        element_type=field.element_type,
        type_name=field.type_name,
    )

    assert parameter.supports_children is supports


@pytest.mark.parametrize(
    "written,element_type",
    [
        ("Array of int64", ParameterType.LONG),
        ("Array of dict", ParameterType.OBJECT),
        ("Array of date", ParameterType.STRING),
    ],
)
def test_an_alias_can_name_what_an_array_holds(written, element_type) -> None:
    """The element is read with the same vocabulary as a whole cell, so a page
    writing `int64` inside an array gets the same answer as one writing it
    alone. Only a word the vocabulary does not know is taken for a structure."""
    field = parse_field_type(written)

    assert field.param_type is ParameterType.ARRAY
    assert field.element_type is element_type
    assert field.type_name is None
