"""Field type parsing and classification from OTC docs."""

from __future__ import annotations

import re

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

#: `List<Node>`, `Map<String, Node>` - generic syntax some api-ref pages use in
#: place of prose. Greedy on purpose, so the inner text of a nested generic
#: reaches `>` rather than stopping at the first one.
_GENERIC_RE = re.compile(
    r"^\s*(?P<container>list|map)\s*<\s*(?P<inner>.+)\s*>\s*$", re.IGNORECASE
)

#: A structure name is one identifier, the way OTC writes them -
#: `CreateFirewallOption`, `RequestTag`. Deliberately not `.+?`: a Type cell
#: reading "Specifies the schedule data structure" is prose, and naming a
#: structure after it would invent a reference the page never made.
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_IDENTIFIER_RE = re.compile(_IDENTIFIER)
_STRUCT_NAME = rf"(?P<name>{_IDENTIFIER})"

#: `Schedule data structure` - a struct name carrying its container as a suffix.
_DATA_STRUCTURE_RE = re.compile(
    rf"^\s*{_STRUCT_NAME}\s+data\s+structure\s*$", re.IGNORECASE
)

#: `Node structure array` - the same, for an array of them.
_STRUCTURE_ARRAY_RE = re.compile(
    rf"^\s*{_STRUCT_NAME}\s+structure\s+array\s*$", re.IGNORECASE
)


def _normalize_named_syntax(raw: str) -> str:
    """Rewrite named container syntax into the prose spelling, or return `raw`.

    `List<Node>` and `Node structure array` both say "array of Node objects",
    and `Schedule data structure` says "Schedule object". Rewriting them into
    that prose leaves one set of rules deciding what a type is: `List<String>`
    then lands on `Array of strings` for the same reason the prose spelling
    does, and the struct name falls out of `STRUCT_KEYWORDS_RE` unchanged.

    Case is preserved, so a caller that needs the struct name gets it spelled as
    the documentation spelled it.
    """
    generic = _GENERIC_RE.match(raw)
    if generic is not None:
        if generic.group("container").lower() == "map":
            # Key and value types are dropped, deliberately: the IR has no map
            # type and may not grow one, and a JSON map is an object.
            return "Object"
        # Nested first, so `List<Map<String, Node>>` becomes an array of objects
        # rather than an array of a struct named `Map<String, Node>`.
        element = _normalize_named_syntax(generic.group("inner").strip())
        if not _IDENTIFIER_RE.fullmatch(element) and _names_a_structure(element):
            # A container this module does not know, like `List<Set<Node>>`.
            # It is still an array, but nothing inside it is a name anyone could
            # look up, and `Set<Node>` is not one.
            return "Array of objects"
        return f"Array of {element} objects"

    named = _DATA_STRUCTURE_RE.match(raw)
    if named is not None and _names_a_structure(named.group("name")):
        return f"{named.group('name')} object"

    named = _STRUCTURE_ARRAY_RE.match(raw)
    if named is not None and _names_a_structure(named.group("name")):
        return f"Array of {named.group('name')} objects"

    return raw


def _names_a_structure(name: str) -> bool:
    """Whether `name` names a structure rather than a type already understood.

    It decides whether a cell is rewritten at all. `Schedule data structure`
    names a structure and `String data structure` does not, so only the first is
    rewritten - the second would turn a string into an object. `List data
    structure` is the same case: it is the legacy spelling of an array, not a
    structure called "List".

    Asked of `classify_type` rather than listed again here, so there stays one
    vocabulary.

    This calls back into `classify_type`, which calls the rewrite again. It
    terminates on nesting depth rather than on length: every step consumes one
    container, and what the rewrite emits carries no named syntax of its own.
    """
    return classify_type(name) is ParameterType.UNKNOWN


def classify_type(raw: str) -> ParameterType:
    """Type-text → ParameterType. Loose matching on lower-cased text."""
    if not raw:
        return ParameterType.UNKNOWN
    lower = raw.strip().lower()

    alias = _ALIASES.get(lower)
    if alias is not None:
        return alias

    # After the aliases: a bare legacy spelling is settled by then, and the
    # rewrite never sees it. Re-lowered because it introduces prose of its own.
    lower = _normalize_named_syntax(lower).lower()

    # Composite array types first (more specific).
    if re.search(r"\barray\s+of\s+strings?\b", lower):
        return ParameterType.ARRAY_OF_STRINGS
    if re.search(r"\barray\s+of\s+integers?\b", lower):
        return ParameterType.ARRAY_OF_INTEGERS
    if re.search(r"\barray\s+of\s+", lower) and "object" in lower:
        return ParameterType.ARRAY_OF_OBJECTS
    if lower.startswith("array of "):
        return ParameterType.ARRAY_OF_OBJECTS  # named struct → object array

    # Bare composites
    if lower == "array" or lower.startswith("array "):
        return ParameterType.ARRAY

    # Primitives — match the longest prefix word.
    for word, kind in (
        ("string", ParameterType.STRING),
        ("long", ParameterType.LONG),
        ("integer", ParameterType.INTEGER),
        ("float", ParameterType.FLOAT),
        ("double", ParameterType.DOUBLE),
        ("boolean", ParameterType.BOOLEAN),
        ("bool", ParameterType.BOOLEAN),
        ("object", ParameterType.OBJECT),
    ):
        if re.search(rf"\b{word}\b", lower):
            return ParameterType.OBJECT if "object" in lower else kind

    return ParameterType.UNKNOWN


# Parameter types that carry a referenced struct name worth preserving.
STRUCT_TYPES = frozenset(
    {
        ParameterType.OBJECT,
        ParameterType.ARRAY,
        ParameterType.ARRAY_OF_OBJECTS,
    }
)


def extract_struct_type_name(raw_type: str) -> str | None:
    """Bare struct name from an object/array type cell, or ``None``.

    An alias names the type itself, so it references no struct: a cell reading
    `dict` would otherwise come back as a reference to a structure called
    "dict", which is a name the documentation never wrote. The legacy spellings
    reach the same answer through `STRUCT_KEYWORDS_RE`, which strips them.
    """
    if raw_type.strip().lower() in _ALIASES:
        return None
    name = STRUCT_KEYWORDS_RE.sub(" ", _normalize_named_syntax(raw_type))
    name = re.sub(r"\s+", " ", name).strip()
    return name or None


def parse_mandatory(text: str) -> bool:
    """Parse mandatory indicator into boolean."""
    cleaned = text.strip().lower()
    return cleaned in {"yes", "true", "required"}
