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


def classify_type(raw: str) -> ParameterType:
    """Type-text → ParameterType. Loose matching on lower-cased text."""
    if not raw:
        return ParameterType.UNKNOWN
    lower = raw.strip().lower()

    alias = _ALIASES.get(lower)
    if alias is not None:
        return alias

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
    name = STRUCT_KEYWORDS_RE.sub(" ", raw_type)
    name = re.sub(r"\s+", " ", name).strip()
    return name or None


def parse_mandatory(text: str) -> bool:
    """Parse mandatory indicator into boolean."""
    cleaned = text.strip().lower()
    return cleaned in {"yes", "true", "required"}
