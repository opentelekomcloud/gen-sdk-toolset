"""Read endpoints of the Generation panel.

Generation itself does not exist yet: what this panel can serve today is which
services it would work on, selected from the stored Scan data. Like the Scan
read routes, these only read what ingest persisted - they never rescan and
never call GitHub.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tools.panel.api.deps import get_db
from tools.panel.api.routes.scan_read import all_services
from tools.panel.api.schemas import GenerationServiceItem
from tools.panel.core.service_state import in_generation_list

router = APIRouter()


@router.get("/generation/services", response_model=list[GenerationServiceItem])
def list_generation_services(
    db: Session = Depends(get_db),
) -> list[GenerationServiceItem]:
    """Services with something to generate, in the Scan registry's order.

    Built on the same set as the Scan registry, so an excluded or ineligible
    service never shows up here; the rule that narrows it lives in
    :func:`tools.panel.core.service_state.in_generation_list`.
    """
    return [
        GenerationServiceItem.from_service(service)
        for service, state in all_services(db)
        if in_generation_list(state)
    ]
