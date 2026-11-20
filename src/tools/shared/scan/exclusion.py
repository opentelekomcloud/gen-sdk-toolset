"""Why a scan left a source path out of production coverage.

A skipped page is a decision, so it is recorded with a machine-readable reason
and the evidence it rests on. A page whose lifecycle notice is not clear enough
to decide on stays in coverage and is listed as a review candidate instead.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class ExclusionReason(StrEnum):
    """Why a source path is outside production coverage."""

    #: A lifecycle label or an operation-wide notice marks it for retirement.
    retired = "retired"
    #: It belongs to a repository of sample material, not a service.
    sample = "sample"
    #: It is a guide page (calling APIs, examples, FAQs), not an operation.
    guide = "guide"
    #: Stored before reasons were recorded; the snapshot kept only the path.
    unrecorded = "unrecorded"


class ExclusionEvidence(BaseModel):
    """What a decision about one path rests on.

    ``source`` is the file or directory the evidence was read from, or the
    setting that holds the rule. ``line`` is 1-based and set only when the
    evidence is a line of a file. ``text`` is the label, notice, segment or
    repository that matched.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    line: int | None = None
    text: str


class ExcludedDocument(BaseModel):
    """One source path a scan did not count, with why."""

    model_config = ConfigDict(extra="forbid")

    path: str
    reason: ExclusionReason
    evidence: ExclusionEvidence | None = None

    @model_validator(mode="after")
    def evidence_matches_reason(self) -> Self:
        # Only a path stored before reasons existed may lack evidence; a scan
        # that decides now always knows what it decided on.
        if (self.reason is ExclusionReason.unrecorded) != (self.evidence is None):
            raise ValueError("evidence is required unless the reason is unrecorded")
        return self


class ReviewCandidate(BaseModel):
    """A counted page whose lifecycle notice was too unclear to exclude it."""

    model_config = ConfigDict(extra="forbid")

    path: str
    evidence: ExclusionEvidence
