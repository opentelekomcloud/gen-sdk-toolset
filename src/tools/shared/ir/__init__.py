from .document import Document
from .endpoint import Endpoint
from .enums import HttpMethod, ParameterType
from .example import Example
from .parameter import Parameter
from .repository import Repository
from .section import Section, SectionName
from .service import Service

#: Version of the serialized Document/Endpoint contract. Bump on any breaking
#: change to the IR models so persisted payloads can be told apart.
DOCUMENT_SCHEMA_VERSION = "1"

__all__ = [
    "DOCUMENT_SCHEMA_VERSION",
    "HttpMethod",
    "ParameterType",
    "Document",
    "Endpoint",
    "Parameter",
    "Example",
    "Repository",
    "Section",
    "SectionName",
    "Service",
]
