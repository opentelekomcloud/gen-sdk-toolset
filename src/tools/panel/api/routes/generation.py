"""Generation panel endpoints that change data.

The start of a service's preliminary grouping, and the edits of the layout it
stores: add, rename and move (ADR-0064). The reads stay in
``generation_read.py``, as the Scan reads stay apart from ``scans.py``.

Each edit changes only the layout tables - ``resource`` and
``resource_endpoint`` - and answers with the whole layout as the read serves
it, so the editor shows the saved state rather than its own guess of it. The
set is closed: no resource is deleted, no endpoint goes back to "unassigned" or
"no version", and nothing resets the layout. A resource whose endpoints all
moved out stays.

A name must be a package name (ADR-0065): the request body checks it against
``RESOURCE_NAME_PATTERN``, so a malformed one is a ``422`` before anything is
read. Whether it is free in its version only the ``resource`` table can say
without a race, so a taken name is the unique violation, answered ``409``.

Every answer - the start's and each edit's - is read while the Service row
is still locked and returned only once the change has committed: built after
the commit, its several queries could each see a different edit of another
worker, and the reply would show a layout that never existed.

Editing a confirmed resource removes its confirmation, and a move removes it
from both resources it touches (ADR-0068); every other resource keeps its own.

A resource is confirmed on its own (ADR-0066), and only while every endpoint
it holds in the active Snapshot - at least one - has ``overall_status`` ``ok``
(ADR-0067). The confirmation takes the same lock as the edits, so no edit,
ingest or activation can slip between the check of those endpoints and the
confirmation written for them. A later ingest or activation that changes those
endpoints drops it again (``switch_active_snapshot``).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tools.panel.api.auth import Identity, require_worker
from tools.panel.api.deps import get_db
from tools.panel.api.routes.generation_read import generation_service
from tools.panel.api.schemas import (
    AddResourceRequest,
    LayoutResponse,
    MoveEndpointRequest,
    RenameResourceRequest,
)
from tools.panel.core.analytics import OverallStatus
from tools.panel.core.db.base import violated_constraint
from tools.panel.core.db.models import (
    RESOURCE_NAME_UNIQUE_IN_VERSION,
    Layout,
    Resource,
    ResourceEndpoint,
    Service,
)
from tools.panel.core.grouping import has_api_version
from tools.panel.core.layout import (
    active_endpoint,
    endpoint_statuses,
    listed_versions,
    service_layout,
    start_layout,
    unconfirm,
)

logger = logging.getLogger(__name__)

#: How many blocking endpoints a refused confirmation names; the rest it counts.
NAMED_BLOCKERS = 5

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
    response = _layout(db, service)
    db.commit()
    return response


@router.post(
    "/generation/services/{repo:path}/layout/resources",
    status_code=201,
    response_model=LayoutResponse,
)
def add_resource(
    repo: str,
    body: AddResourceRequest,
    identity: Identity = Depends(require_worker),
    db: Session = Depends(get_db),
) -> LayoutResponse:
    """Add an empty resource to a version the layout already lists.

    Only such a version - the versions of its resources and of its
    "unassigned" endpoints: adding a version is not among the edits.
    """
    service = _editable_service(db, repo)
    if body.api_version not in listed_versions(db, service):
        raise HTTPException(
            status_code=409,
            detail=f"The layout of {repo} has no version {body.api_version}",
        )

    db.add(
        Resource(service_id=service.id, api_version=body.api_version, name=body.name)
    )
    response = _save(db, service, name=body.name, api_version=body.api_version)
    logger.info(
        "service %s: resource %s added to %s by %s",
        repo,
        body.name,
        body.api_version,
        identity.name,
    )
    return response


@router.post(
    "/generation/services/{repo:path}/layout/resources/{resource_id}/rename",
    response_model=LayoutResponse,
)
def rename_resource(
    repo: str,
    resource_id: int,
    body: RenameResourceRequest,
    identity: Identity = Depends(require_worker),
    db: Session = Depends(get_db),
) -> LayoutResponse:
    """Give a resource a new name; its ``id`` stays, so links to it do too.

    Renaming to the name it already has changes nothing, so its confirmation
    stays as well.
    """
    service = _editable_service(db, repo)
    resource = _resource_or_404(db, service, resource_id)
    if resource.name == body.name:
        return _unchanged(db, service)

    resource.name = body.name
    unconfirm(resource)
    response = _save(db, service, name=body.name, api_version=resource.api_version)
    logger.info(
        "service %s: resource %s renamed to %s by %s",
        repo,
        resource_id,
        body.name,
        identity.name,
    )
    return response


@router.post(
    "/generation/services/{repo:path}/layout/endpoints/move",
    response_model=LayoutResponse,
)
def move_endpoint(
    repo: str,
    body: MoveEndpointRequest,
    identity: Identity = Depends(require_worker),
    db: Session = Depends(get_db),
) -> LayoutResponse:
    """Put one endpoint of the active Snapshot into a resource of the layout.

    The endpoint never leaves its version (ADR-0064): one in a resource moves
    only within that resource's version, one in "unassigned" only into its own
    version, and one in "no version" into any version - the user sets the
    version the scanner did not find. An empty version is no version, as in
    the grouping and the read. Moving it into the resource it is in changes
    nothing.
    """
    service = _editable_service(db, repo)
    target = _resource_or_404(db, service, body.resource_id)
    endpoint = active_endpoint(db, service, body.path)
    if endpoint is None:
        raise HTTPException(
            status_code=404,
            detail=f"Endpoint {body.path} not found in the active snapshot of {repo}",
        )

    link = db.get(ResourceEndpoint, (service.id, body.path))
    source = link.resource if link is not None else None
    if source is not None and source.id == target.id:
        return _unchanged(db, service)

    version = source.api_version if source is not None else endpoint.api_version
    if has_api_version(version) and version != target.api_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Endpoint {body.path} is in {version}; it cannot move to "
                f"resource {target.name} in {target.api_version}"
            ),
        )

    if link is None:
        db.add(
            ResourceEndpoint(
                service_id=service.id, path=body.path, resource_id=target.id
            )
        )
    else:
        link.resource = target
        unconfirm(source)
    unconfirm(target)
    response = _save(db, service)
    logger.info(
        "service %s: endpoint %s moved to resource %s by %s",
        repo,
        body.path,
        target.id,
        identity.name,
    )
    return response


@router.post(
    "/generation/services/{repo:path}/layout/resources/{resource_id}/confirm",
    response_model=LayoutResponse,
)
def confirm_resource(
    repo: str,
    resource_id: int,
    identity: Identity = Depends(require_worker),
    db: Session = Depends(get_db),
) -> LayoutResponse:
    """Confirm one resource, leaving every other resource as it is (ADR-0066).

    Only a resource with at least one endpoint in the active Snapshot, all of
    them ``ok`` (ADR-0067); otherwise a ``409`` that names what blocks it, and
    nothing changes - other resources stay confirmable. Confirming a confirmed
    resource changes nothing either: ``confirmed_by`` and ``confirmed_at`` keep
    the first confirmation, the one that checked these endpoints.

    ``confirmed_at`` is when the request came, not when the lock was granted.
    """
    requested_at = datetime.now(tz=UTC)
    service = _editable_service(db, repo)
    resource = _resource_or_404(db, service, resource_id)
    if resource.confirmed_by is not None:
        return _unchanged(db, service)

    statuses = endpoint_statuses(db, service, resource)
    if not statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Resource {resource.name} has no endpoint in the active snapshot",
        )
    not_ok = sorted(
        path for path, status in statuses.items() if status != OverallStatus.OK
    )
    if not_ok:
        # how many block it, and the first few by path: enough to act on
        named = ", ".join(not_ok[:NAMED_BLOCKERS])
        more = len(not_ok) - NAMED_BLOCKERS
        raise HTTPException(
            status_code=409,
            detail=(
                f"Resource {resource.name} has {len(not_ok)} endpoint(s) that are "
                f"not ok: {named}" + (f" and {more} more" if more > 0 else "")
            ),
        )

    resource.confirmed_by = identity.name
    resource.confirmed_at = requested_at
    response = _save(db, service)
    logger.info(
        "service %s: resource %s confirmed by %s", repo, resource_id, identity.name
    )
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _editable_service(db: Session, repo: str) -> Service:
    """The Service whose layout an edit may change, locked until it commits.

    Off the Generation list is a ``404``, as for the layout read. On it but
    without a ``layout`` row is a ``409``: the layout starts only from the
    preliminary grouping, never from an edit.

    The lock is the one the layout start, activation and exclusion take, and it
    holds off a scan's ingest as well: replacing the active Snapshot writes
    this row, which waits until the edit commits. So the Snapshot an edit
    checks the endpoint against is still the active one when it commits.
    """
    db.execute(select(Service.id).where(Service.repo == repo).with_for_update())
    service = generation_service(db, repo)
    if db.get(Layout, service.id) is None:
        raise HTTPException(
            status_code=409,
            detail=f"Service {repo} has no layout yet; its grouping has not run",
        )
    return service


def _resource_or_404(db: Session, service: Service, resource_id: int) -> Resource:
    """A resource of this service's layout; one of another service is unknown here."""
    resource = db.scalar(
        select(Resource).where(
            Resource.id == resource_id,
            Resource.service_id == service.id,
        )
    )
    if resource is None:
        raise HTTPException(
            status_code=404,
            detail=f"Resource {resource_id} not found for service {service.repo}",
        )
    return resource


def _save(
    db: Session,
    service: Service,
    *,
    name: str | None = None,
    api_version: str | None = None,
) -> LayoutResponse:
    """Write the edit, read the layout back under the lock, then commit.

    The write is flushed and the session expired first, so the read sees this
    transaction's rows rather than objects the session loaded before the edit.
    The answer exists only if the commit succeeds: a commit that fails leaves
    the caller nothing claiming the edit was saved.

    A taken name - the unique violation, told apart by the name the database
    reports - is a ``409``. Any other violation is no fault of the request, so
    it is raised as is and answers ``500`` rather than a refusal blaming it.
    """
    try:
        db.flush()
        db.expire_all()
        response = _layout(db, service)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if name is not None and (
            violated_constraint(exc) == RESOURCE_NAME_UNIQUE_IN_VERSION.name
        ):
            raise HTTPException(
                status_code=409,
                detail=f"A resource named {name!r} already exists in {api_version}",
            ) from exc
        raise
    return response


def _layout(db: Session, service: Service) -> LayoutResponse:
    return LayoutResponse.from_layout(service_layout(db, service))


def _unchanged(db: Session, service: Service) -> LayoutResponse:
    """The layout after an edit that writes nothing, read while still locked.

    Read before the transaction ends, like the answer to an edit that writes;
    the lock is released once it is built.
    """
    response = _layout(db, service)
    db.rollback()
    return response
