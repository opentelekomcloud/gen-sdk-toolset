from typing import Annotated, Literal

from pydantic import Field

from .document import Document
from .endpoint import Endpoint
from .repository import Repository

DocumentEntity = Annotated[Document | Endpoint, Field(discriminator="kind")]


class Service(Repository):
    kind: Literal["service"] = "service"
    documents: list[DocumentEntity] = Field(default_factory=list)

    @property
    def endpoints(self) -> list[Endpoint]:
        return [
            document for document in self.documents if isinstance(document, Endpoint)
        ]


RepositoryEntity = Annotated[Repository | Service, Field(discriminator="kind")]
