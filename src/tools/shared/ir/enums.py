from enum import Enum


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ParameterType(str, Enum):
    """Types found in OTC docs parameter tables."""

    STRING = "String"
    INTEGER = "Integer"
    LONG = "Long"
    FLOAT = "Float"
    DOUBLE = "Double"
    BOOLEAN = "Boolean"
    OBJECT = "Object"
    ARRAY = "Array"
    # Composite types parsed from docs like "Array of strings"
    ARRAY_OF_STRINGS = "Array of strings"
    ARRAY_OF_OBJECTS = "Array of objects"
    ARRAY_OF_INTEGERS = "Array of integers"
    # Fallback for anything the parser can't classify
    UNKNOWN = "Unknown"

    @property
    def supports_children(self) -> bool:
        return self in {self.OBJECT, self.ARRAY, self.ARRAY_OF_OBJECTS}
