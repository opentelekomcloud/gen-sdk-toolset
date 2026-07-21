"""Field type parsing and classification from OTC docs."""

from __future__ import annotations

import re

from tools.shared.ir import ParameterType

from .patterns import STRUCT_KEYWORDS_RE


def classify_type(raw: str) -> ParameterType:
    """Type-text → ParameterType. Loose matching on lower-cased text."""
    if not raw:
        return ParameterType.UNKNOWN
    lower = raw.strip().lower()

    if lower in {"list", "list data structure"}:
        return ParameterType.ARRAY
    if lower in {"dictionary", "data structure"}:
        return ParameterType.OBJECT

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
    """Bare struct name from an object/array type cell, or ``None``."""
    name = STRUCT_KEYWORDS_RE.sub(" ", raw_type)
    name = re.sub(r"\s+", " ", name).strip()
    return name or None


def parse_mandatory(text: str) -> bool:
    """Parse mandatory indicator into boolean."""
    cleaned = text.strip().lower()
    return cleaned in {"yes", "true", "required"}
