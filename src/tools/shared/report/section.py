"""Per-section data: extracted content + field-level metrics."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tools.shared.ir import Parameter
from tools.shared.report.enums import SectionStatus

from tools.shared.report.issue import Issue


class ExampleBlock(BaseModel):
    """One example code block (request or response).

    Stored as both raw text and best-effort parsed JSON. `parsed` is
    ``None`` whenever the code block isn't valid JSON — many OTC examples
    are wire-format HTTP, cURL fragments, or JSON with stray comments.
    """

    raw: str
    language: str | None = None
    parsed: dict | list | None = None
    label: str | None = None  # e.g. "Specifying versionId to Delete a Specific Version"


class SectionResult(BaseModel):
    """Result of attempting to extract one content section of a doc.

    Carries both the extracted data (``parameters`` / ``examples``) and
    the quality metrics. The two live together so consumers don't have
    to join across separate stores.
    """

    status: SectionStatus
    issues: list[Issue] = Field(default_factory=list)

    # Extracted content. Empty for sections that are MISSING / SKIPPED /
    # not parameter-bearing (e.g. example_* sections use `examples`).
    parameters: list[Parameter] = Field(default_factory=list)
    examples: list[ExampleBlock] = Field(default_factory=list)

    # (fields_recognized + fields_unknown_type + fields_failed) == fields_total
    fields_total: int = 0  # number of rows in the table(s) we walked
    fields_recognized: int = 0  # rows with a non-empty name AND a non-empty type cell
    fields_unknown_type: int = 0  # rows with a name but a type we couldn't classify
    fields_failed: int = 0  # rows we couldn't parse at all
