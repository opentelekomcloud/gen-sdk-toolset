from typing import Any, Literal

from pydantic import Field, SerializeAsAny, field_validator

from .document import Document
from .endpoint import Endpoint
from .repository import Repository


class Service(Repository):
    kind: Literal["service"] = "service"
    documents: list[SerializeAsAny[Document]] = Field(default_factory=list)

    @field_validator("documents", mode="before")
    @classmethod
    def restore_endpoint_subclasses(cls, documents: Any) -> Any:
        if not isinstance(documents, list):
            return documents
        return [
            Endpoint.model_validate(document)
            if isinstance(document, dict) and document.get("kind") == "endpoint"
            else document
            for document in documents
        ]

    @property
    def endpoints(self) -> list[Endpoint]:
        return [
            document for document in self.documents if isinstance(document, Endpoint)
        ]
