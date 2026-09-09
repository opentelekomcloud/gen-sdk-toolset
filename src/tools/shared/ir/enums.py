from enum import StrEnum


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ParameterType(StrEnum):
    """One type kind found in OTC docs parameter tables.

    A kind only: what an array *contains* is `Parameter.element_type`, not a
    member here. The composite `ARRAY_OF_*` members this replaces could name
    three element types and no others, so `Array of booleans` had to be filed
    under `Array of objects` - a wrong answer that then invited "booleans" into
    `type_name` as though a structure by that name existed.
    """

    STRING = "String"
    INTEGER = "Integer"
    LONG = "Long"
    FLOAT = "Float"
    DOUBLE = "Double"
    BOOLEAN = "Boolean"
    OBJECT = "Object"
    ARRAY = "Array"
    # Fallback for anything the parser can't classify
    UNKNOWN = "Unknown"


#: What an array may be documented as holding. Every kind except `ARRAY` - the
#: IR does not nest arrays - and `UNKNOWN`, which is the absence of an answer
#: and is spelled `element_type=None` instead.
ELEMENT_TYPES: frozenset[ParameterType] = frozenset(
    {
        ParameterType.STRING,
        ParameterType.INTEGER,
        ParameterType.LONG,
        ParameterType.FLOAT,
        ParameterType.DOUBLE,
        ParameterType.BOOLEAN,
        ParameterType.OBJECT,
    }
)
