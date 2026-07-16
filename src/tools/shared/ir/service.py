from pydantic import Field, field_serializer, field_validator

from .document import Document
from .endpoint import Endpoint
from .repository import Repository


class Service(Repository):
    documents: list[Document] = Field(default_factory=list)

    @field_validator("documents", mode="before")
    @classmethod
    def restore_endpoints(cls, documents):
        return [
            Endpoint.model_validate(document)
            if isinstance(document, dict)
            and "method" in document
            and "uri" in document
            else document
            for document in documents
        ]

    @field_serializer("documents")
    def serialize_documents(self, documents: list[Document]) -> list[dict]:
        return [document.model_dump(mode="json") for document in documents]

    @property
    def endpoints(self) -> list[Endpoint]:
        return [
            document for document in self.documents if isinstance(document, Endpoint)
        ]
