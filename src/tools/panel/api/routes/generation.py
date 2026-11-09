"""Generation panel endpoints that change data.

Today that is the start of a service's preliminary grouping. The reads stay in
``generation_read.py``, as the Scan reads stay apart from ``scans.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tools.panel.api.auth import Identity, require_worker
from tools.panel.api.deps import get_db
from tools.panel.api.routes.generation_read import generation_service
from tools.panel.api.schemas import LayoutResponse
from tools.panel.core.db.models import Layout, Service
from tools.panel.core.layout import service_layout, start_layout

router = APIRouter()


@router.post(
    "/generation/services/{repo:path}/layout",
    status_code=201,
    response_model=LayoutResponse,
)
def start_service_layout(
    repo: str,
    identity: Identity = Depends(require_worker),
    db: Session = Depends(get_db),
) -> LayoutResponse:
    """Run the preliminary grouping of a service and answer with its layout.

    Runs within the request: the rule reads stored columns only and calls
    nothing outside the database, so there is no Job to poll. The answer is
    what the layout read serves afterwards.

    A repository off the Generation list is a ``404``, as for the read. A
    service that already has a layout - even one without a resource - is a
    ``409``: a layout changes only by editing (ADR-0072). That refusal comes
    from the ``layout`` primary key, not from a check before the insert, so two
    concurrent starts cannot both store one. A failure commits nothing: the
    service stays without a layout and the start can be retried (ADR-0061).
    """
    # Held until the commit, as snapshot activation and ingest hold it: the
    # active snapshot grouped below cannot change before the layout is stored.
    db.execute(select(Service.id).where(Service.repo == repo).with_for_update())
    service = generation_service(db, repo)
    service_id = service.id
    try:
        start_layout(db, service, created_by=identity.name)
    except IntegrityError as exc:
        db.rollback()
        if db.get(Layout, service_id) is None:
            raise
        raise HTTPException(
            status_code=409,
            detail=f"Service {repo} already has a layout",
        ) from exc
    db.commit()
    return LayoutResponse.from_layout(service_layout(db, service))
