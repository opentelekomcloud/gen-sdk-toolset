from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

#: What the panel cannot do after a failed startup cleanup. Deliberately fixed
#: text rather than the exception: `/health` is unauthenticated, and a database
#: error message carries the host and user it failed to connect as.
CLEANUP_FAILED_DETAIL = (
    "startup job cleanup failed: jobs left running by a previous process were "
    "not closed, so their services may refuse a rescan until those jobs are "
    "cancelled"
)


class HealthResponse(BaseModel):
    """Whether the panel is fully functional, not merely running.

    ``degraded`` still answers ``200``: the panel serves every read endpoint in
    that state, and this response is what a container healthcheck polls. Failing
    the check would stop the frontend from starting over a janitorial problem,
    which is a worse outcome than the problem.
    """

    status: Literal["ok", "degraded"]
    detail: str | None = None


@router.get("/health")
def health(request: Request) -> HealthResponse:
    """Report liveness, and any capability the panel knows it is missing."""
    if getattr(request.app.state, "startup_cleanup_failed", False):
        return HealthResponse(status="degraded", detail=CLEANUP_FAILED_DETAIL)
    return HealthResponse(status="ok")
