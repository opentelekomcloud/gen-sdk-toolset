"""Field type parsing and classification from OTC docs.

One cell of a Type column yields three facts at once - the type, what an array
holds, and the structure it refers to - so one function produces all three.
Deriving them separately is how they come to disagree: an earlier version
classified `Array of booleans` as an object array in one place and pulled
"booleans" out as a structure name in another, and neither half could see that
the other was wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tools.shared.ir import ParameterType

from .patterns import STRUCT_KEYWORDS_RE

#: Spellings the documentation uses for types the IR already has. The legacy OTC
#: wording and the programming-language shorthand sit in one table because they
#: are the same fact: `Dictionary` and `dict` are both somebody's word for an
#: object, and one table is what stops the two from drifting apart.
#:
#: **These are conventions, not corrections.** A writer choosing `int64` picked a
#: real type name; a writer typing `Interger` made a mistake, and the scanner
#: reports it (`UNKNOWN_TYPE_FORMAT`) rather than guessing what was meant.
#: Adding a misspelling here would silently absorb exactly the defect this
#: project exists to count.
#:
#: Matched whole, and only whole: `date` is a type, while "creation date" is a
#: description that happens to contain one, and matching inside prose would type
#: half a table from its wording.
_ALIASES: dict[str, ParameterType] = {
    # Legacy OTC spellings.
    "list": ParameterType.ARRAY,
    "list data structure": ParameterType.ARRAY,
    "dictionary": ParameterType.OBJECT,
    "data structure": ParameterType.OBJECT,
    # Widths, as the API references write them.
    "int": ParameterType.INTEGER,
    "int32": ParameterType.INTEGER,
    "int64": ParameterType.LONG,
    "number": ParameterType.INTEGER,
    # Mapping types, however the page spells them.
    "dict": ParameterType.OBJECT,
    "json": ParameterType.OBJECT,
    "map": ParameterType.OBJECT,
    "jsonarray": ParameterType.ARRAY,
    # Dates and times arrive as text: OTC documents them as formatted strings,
    # never as a distinct type, so a generator would emit `str` either way.
    "date": ParameterType.STRING,
    "timestamp": ParameterType.STRING,
}

#: Primitive words, longest-first so `bool` cannot win inside `boolean`.
_PRIMITIVES: tuple[tuple[str, ParameterType], ...] = (
    ("string", ParameterType.STRING),
    ("long", ParameterType.LONG),
    ("integer", ParameterType.INTEGER),
    ("float", ParameterType.FLOAT),
    ("double", ParameterType.DOUBLE),
    ("boolean", ParameterType.BOOLEAN),
    ("bool", ParameterType.BOOLEAN),
    ("object", ParameterType.OBJECT),
)

#: `Array of strings`, `Array of booleans`, ... - the element the prose names.
#: Plural or singular, because both spellings occur.
_ELEMENT_WORDS: tuple[tuple[str, ParameterType], ...] = (
    ("strings", ParameterType.STRING),
    ("integers", ParameterType.INTEGER),
    ("longs", ParameterType.LONG),
    ("floats", ParameterType.FLOAT),
    ("doubles", ParameterType.DOUBLE),
    ("booleans", ParameterType.BOOLEAN),
    ("bools", ParameterType.BOOLEAN),
    ("objects", ParameterType.OBJECT),
)

#: A structure name is one identifier, the way OTC writes them -
#: `CreateFirewallOption`, `RequestTag`. Deliberately not `.+?`: a Type cell
#: reading "Specifies the schedule data structure" is prose, and naming a
#: structure after it would invent a reference the page never made.
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_STRUCT_NAME = rf"(?P<name>{_IDENTIFIER})"

#: `List<Node>` and `Map<String, Node>`, and nothing looser. One identifier per
#: type argument means `List<>`, `List<   >`, `Map<Node>` and `List<Node>>` do
#: not match, and stay `Unknown` where they are counted - which is the honest
#: answer for syntax nobody can read. Nested generics land there too: an array
#: of maps is representable only by guessing which of them the row meant.
_LIST_RE = re.compile(rf"^\s*list\s*<\s*({_IDENTIFIER})\s*>\s*$", re.IGNORECASE)
_MAP_RE = re.compile(
    rf"^\s*map\s*<\s*{_IDENTIFIER}\s*,\s*{_IDENTIFIER}\s*>\s*$", re.IGNORECASE
)

#: `Schedule data structure` - a struct name carrying its container as a suffix.
_DATA_STRUCTURE_RE = re.compile(
    rf"^\s*{_STRUCT_NAME}\s+data\s+structure\s*$", re.IGNORECASE
)

#: `Node structure array` - the same, for an array of them.
_STRUCTURE_ARRAY_RE = re.compile(
    rf"^\s*{_STRUCT_NAME}\s+structure\s+array\s*$", re.IGNORECASE
)

#: `Array of <something>` - the prose form, whatever follows.
_ARRAY_OF_RE = re.compile(r"^\s*array\s+of\s+(?P<element>.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class FieldType:
    """Everything one Type cell says about a parameter."""

    param_type: ParameterType = ParameterType.UNKNOWN
    #: What an array holds. `None` on an array means the cell did not say.
    element_type: ParameterType | None = None
    #: The documented structure the cell refers to, if it names one.
    type_name: str | None = None


def parse_field_type(raw: str) -> FieldType:
    """Read one Type cell.

    The order is the whole design. Whole-cell aliases settle the bare legacy
    spellings first, so `List data structure` stays an array rather than being
    read as a structure called "List". The named syntax comes next, because
    `Node structure array` is a shape no prose rule matches. Prose is last, and
    is where the great majority of cells are answered.
    """
    if not raw or not raw.strip():
        return FieldType()
    text = raw.strip()
    lower = text.lower()

    alias = _ALIASES.get(lower)
    if alias is not None:
        return FieldType(param_type=alias)

    named = _named_syntax(text)
    if named is not None:
        return named

    if "<" in text or ">" in text:
        # Generic syntax the strict forms above could not read. Prose matching
        # would find `String` inside `List<Map<String, Node>>` and call the row
        # a string; `Unknown` says what is true and gets the row counted.
        return FieldType()

    return _prose(text, lower)


def classify_type(raw: str) -> ParameterType:
    """The type kind of one cell, ignoring what an array holds."""
    return parse_field_type(raw).param_type


def extract_struct_type_name(raw_type: str) -> str | None:
    """The documented structure a cell refers to, or ``None``."""
    return parse_field_type(raw_type).type_name


def parse_mandatory(text: str) -> bool:
    """Parse mandatory indicator into boolean."""
    cleaned = text.strip().lower()
    return cleaned in {"yes", "true", "required"}


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _named_syntax(text: str) -> FieldType | None:
    """`List<X>`, `Map<K, V>`, `X data structure`, `X structure array`."""
    listed = _LIST_RE.match(text)
    if listed is not None:
        return _array_of(listed.group(1))

    if _MAP_RE.match(text) is not None:
        # Key and value types are dropped, deliberately: the IR has no map type
        # and is not growing one here, and a JSON map is an object.
        return FieldType(param_type=ParameterType.OBJECT)

    named = _DATA_STRUCTURE_RE.match(text)
    if named is not None and _names_a_structure(named.group("name")):
        return FieldType(param_type=ParameterType.OBJECT, type_name=named.group("name"))

    named = _STRUCTURE_ARRAY_RE.match(text)
    if named is not None and _names_a_structure(named.group("name")):
        return _array_of(named.group("name"))

    return None


def _prose(text: str, lower: str) -> FieldType:
    """`Array of X`, `X object`, `Array`, and the bare primitives."""
    array_of = _ARRAY_OF_RE.match(text)
    if array_of is not None:
        return _array_of(array_of.group("element"))

    if lower == "array" or lower.startswith("array "):
        return FieldType(param_type=ParameterType.ARRAY)

    for word, kind in _PRIMITIVES:
        if re.search(rf"\b{word}\b", lower):
            if "object" in lower:
                return FieldType(
                    param_type=ParameterType.OBJECT, type_name=_struct_name(text)
                )
            return FieldType(param_type=kind)

    return FieldType()


def _array_of(element: str) -> FieldType:
    """An array, typed by whatever its element text names.

    A primitive element is recorded as one and names no structure - `Array of
    booleans` holds booleans, and there is no structure called "booleans" for a
    generator to look up. Anything the parser does not recognise is taken to be
    a documented structure, which is what `Array of RequestTag objects` and
    `List<Node>` both are.
    """
    cleaned = element.strip()
    lower = cleaned.lower()

    for word, kind in _ELEMENT_WORDS:
        if re.search(rf"\b{word[:-1]}s?\b", lower):
            if kind is ParameterType.OBJECT:
                return FieldType(
                    param_type=ParameterType.ARRAY,
                    element_type=ParameterType.OBJECT,
                    type_name=_struct_name(cleaned),
                )
            return FieldType(param_type=ParameterType.ARRAY, element_type=kind)

    if not _names_a_structure(cleaned):
        # A type word the element rule above does not spell, such as the
        # singular `Array of string`. It is that type, not a structure.
        return FieldType(
            param_type=ParameterType.ARRAY, element_type=classify_type(cleaned)
        )

    return FieldType(
        param_type=ParameterType.ARRAY,
        element_type=ParameterType.OBJECT,
        type_name=_struct_name(cleaned),
    )


def _struct_name(text: str) -> str | None:
    """The bare structure name in `text`, once the container words come out."""
    name = re.sub(r"\s+", " ", STRUCT_KEYWORDS_RE.sub(" ", text)).strip()
    return name if name and _names_a_structure(name) else None


def _names_a_structure(name: str) -> bool:
    """Whether `name` names a structure rather than a type already understood.

    `Schedule data structure` names a structure and `String data structure` does
    not, so only the first is read as one - the second would turn a string into
    an object. `List data structure` is the same case: the legacy spelling of an
    array, not a structure called "List".

    Asked of `classify_type` rather than listed again here, so there stays one
    vocabulary. It terminates because a name is a single identifier, which
    carries no named syntax for the parse to descend into.
    """
    return classify_type(name) is ParameterType.UNKNOWN
