"""Read endpoints of the Generation panel.

Generation itself does not exist yet: what this panel can serve today is which
services it would work on, selected from the stored Scan data, and the resource
layout of each. Like the Scan read routes, these only read what is persisted -
they never rescan and never call GitHub.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from tools.panel.api.deps import get_db
from tools.panel.api.routes.scan_read import (
    all_services,
    counted_service,
    matches_search,
)
from tools.panel.api.schemas import GenerationServiceItem, LayoutResponse
from tools.panel.core.layout import service_layout
from tools.panel.core.service_state import in_generation_list

router = APIRouter()


@router.get("/generation/services", response_model=list[GenerationServiceItem])
def list_generation_services(
    db: Session = Depends(get_db),
    q: str = Query(default=""),
) -> list[GenerationServiceItem]:
    """Services with something to generate, in the Scan registry's order.

    Built on the same set as the Scan registry, so an excluded or ineligible
    service never shows up here; the rule that narrows it lives in
    :func:`tools.panel.core.service_state.in_generation_list`.
    """
    return [
        GenerationServiceItem.from_service(service)
        for service, state in all_services(db)
        if in_generation_list(state) and matches_search(service, q)
    ]


@router.get("/generation/services/{repo:path}/layout", response_model=LayoutResponse)
def get_service_layout(repo: str, db: Session = Depends(get_db)) -> LayoutResponse:
    """The resource layout of a service on the Generation list.

    A repository off that list - unknown, excluded, ineligible or without
    endpoints in its active snapshot - answers 404, the same as its pages do.
    """
    found = counted_service(db, repo)
    if found is None or not in_generation_list(found[1]):
        raise HTTPException(status_code=404, detail="Service not found")
    return LayoutResponse.from_layout(service_layout(db, found[0]))
