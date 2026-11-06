"""Edits of a service's resource layout: add, rename and move (ADR-0064).

Each edit changes only the layout tables - ``resource`` and
``resource_endpoint`` - and answers with the whole layout as the read serves
it, so the editor shows the saved state rather than its own guess of it. The
set is closed: no resource is deleted, no endpoint goes back to "unassigned" or
"no version", and nothing resets the layout. A resource whose endpoints all
moved out stays.

A name is checked by the ``resource`` table alone - a package name, free in its
version (ADR-0065) - and a violation is a ``409``. Checking it here first would
be a second copy of the rule and, for the free name, a race.

Editing a confirmed resource removes its confirmation, and a move removes it
from both resources it touches (ADR-0068); every other resource keeps its own.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tools.panel.api.auth import Identity, require_worker
from tools.panel.api.deps import get_db
from tools.panel.api.routes.scan_read import counted_service
from tools.panel.api.schemas import (
    AddResourceRequest,
    LayoutResponse,
    MoveEndpointRequest,
    RenameResourceRequest,
)
from tools.panel.core.db.base import violated_constraint
from tools.panel.core.db.models import (
    RESOURCE_NAME_IS_PACKAGE_NAME,
    RESOURCE_NAME_UNIQUE_IN_VERSION,
    Layout,
    Resource,
    ResourceEndpoint,
    Service,
)
from tools.panel.core.layout import active_endpoint, listed_versions, service_layout
from tools.panel.core.service_state import in_generation_list

logger = logging.getLogger(__name__)

router = APIRouter()


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
    _commit_name(db, name=body.name, api_version=body.api_version)
    logger.info(
        "service %s: resource %s added to %s by %s",
        repo,
        body.name,
        body.api_version,
        identity.name,
    )
    return _layout(db, service)


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
    _unconfirm(resource)
    _commit_name(db, name=body.name, api_version=resource.api_version)
    logger.info(
        "service %s: resource %s renamed to %s by %s",
        repo,
        resource_id,
        body.name,
        identity.name,
    )
    return _layout(db, service)


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
    version the scanner did not find. Moving it into the resource it is in
    changes nothing.
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
    if version is not None and version != target.api_version:
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
        _unconfirm(source)
    _unconfirm(target)
    db.commit()
    logger.info(
        "service %s: endpoint %s moved to resource %s by %s",
        repo,
        body.path,
        target.id,
        identity.name,
    )
    return _layout(db, service)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _editable_service(db: Session, repo: str) -> Service:
    """The Service whose layout an edit may change, locked until it commits.

    Off the Generation list is a ``404``, as for the layout read. On it but
    without a ``layout`` row is a ``409``: the layout starts only from the
    preliminary grouping, never from an edit.

    The lock is the one activation and exclusion take, and it holds off a
    scan's ingest as well: replacing the active Snapshot writes this row, which
    waits until the edit commits. So the Snapshot an edit checks the endpoint
    against is still the active one when it commits.
    """
    locked = db.scalar(select(Service).where(Service.repo == repo).with_for_update())
    found = counted_service(db, repo) if locked is not None else None
    if found is None or not in_generation_list(found[1]):
        raise HTTPException(status_code=404, detail="Service not found")
    service = found[0]
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


def _unconfirm(resource: Resource) -> None:
    """Drop a resource's confirmation (ADR-0068); both columns go together."""
    resource.confirmed_by = None
    resource.confirmed_at = None


def _commit_name(db: Session, *, name: str, api_version: str) -> None:
    """Commit a new or changed resource name, the table deciding if it is valid.

    The two name constraints are a ``409``, told apart by the name the database
    reports. Any other violation is not the user's name at fault, so it is
    raised as is and answers ``500`` rather than a refusal that blames them.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        violated = violated_constraint(exc)
        if violated == RESOURCE_NAME_IS_PACKAGE_NAME.name:
            detail = (
                f"Resource name {name!r} is not a package name: lowercase letters, "
                "digits and underscores, starting with a letter"
            )
        elif violated == RESOURCE_NAME_UNIQUE_IN_VERSION.name:
            detail = f"A resource named {name!r} already exists in {api_version}"
        else:
            raise
        raise HTTPException(status_code=409, detail=detail) from exc


def _layout(db: Session, service: Service) -> LayoutResponse:
    return LayoutResponse.from_layout(service_layout(db, service))


def _unchanged(db: Session, service: Service) -> LayoutResponse:
    """The layout after an edit that writes nothing.

    The transaction ends first, as a commit ends it for an edit that writes:
    the Service row stays locked only for the check, not while the whole
    layout is read back.
    """
    db.rollback()
    return _layout(db, service)
