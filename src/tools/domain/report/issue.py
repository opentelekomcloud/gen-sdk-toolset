"""Structured issue record."""

from __future__ import annotations

from pydantic import BaseModel

from .enums import IssueCode


class Issue(BaseModel):
    """A single problem encountered while processing a doc.

    `code` is queryable; `location` gives a human breadcrumb
    (e.g. "Table 3" or "row 5"); `details` carries free-text context
    that isn't structured but is invaluable when debugging.
    """

    code: IssueCode
    location: str | None = None
    details: str | None = None
