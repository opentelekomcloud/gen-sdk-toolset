from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StatusCode(BaseModel):
    """One row of a status-code table.

    Deliberately not a :class:`Parameter`. A status code is not a field of a
    request or a response body: it has no type, cannot be mandatory, and holds
    no children. Reusing `Parameter` would give it all three and leave every
    consumer guessing which of them mean anything here.

    ``code`` stays a string because the documentation writes it as text -
    ``200`` in most tables, but ``2xx`` and ``4xx`` appear too, and narrowing to
    an integer would turn those rows into parse failures over formatting.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str = ""
