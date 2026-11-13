"""A service's layout: which of its endpoints form which resource.

Stored resources are matched to the active Snapshot's endpoint documents by
path; a path that Snapshot lacks is left out. The "unassigned" and "no version"
lists are derived here, never stored, so they follow the active Snapshot.

A layout is created once, by the preliminary grouping (:func:`start_layout`);
after that its grouping changes only by editing (ADR-0072). A confirmation can
also be dropped when the active Snapshot moves and changes the endpoints it
covered or leaves one of them not ``ok`` (:func:`switch_active_snapshot`,
ADR-0067, ADR-0068).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload, undefer

from tools.panel.core.analytics import OverallStatus
from tools.panel.core.db.models import (
    DocumentRecord,
    Layout,
    Resource,
    ResourceEndpoint,
    Service,
)
from tools.panel.core.grouping import group_endpoints, has_api_version
from tools.shared.ir import ENDPOINT_KIND

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlacedResource:
    """A resource with the endpoints of the active Snapshot it holds."""

    resource: Resource
    endpoints: list[DocumentRecord]


@dataclass(frozen=True)
class LayoutVersion:
    """One API version of the layout: its resources and its unassigned endpoints."""

    api_version: str
    resources: list[PlacedResource]
    unassigned: list[DocumentRecord]


@dataclass(frozen=True)
class ServiceLayout:
    """The layout of one service as the active Snapshot sees it.

    A service has a layout once its ``Layout`` row exists, with or without a
    resource; without one, the versions and lists are empty.
    """

    has_layout: bool
    versions: list[LayoutVersion]
    no_version: list[DocumentRecord]


def service_layout(db: Session, service: Service) -> ServiceLayout:
    """Read the layout of ``service`` against its active Snapshot."""
    if db.get(Layout, service.id) is None:
        return ServiceLayout(has_layout=False, versions=[], no_version=[])

    resources = db.scalars(
        select(Resource)
        .where(Resource.service_id == service.id)
        .options(selectinload(Resource.endpoints))
        .order_by(Resource.api_version, Resource.name)
    ).all()

    documents = db.scalars(
        _active_endpoints(service).options(undefer(DocumentRecord.payload))
    ).all()
    by_path = {document.path: document for document in documents}
    placed_paths = {link.path for resource in resources for link in resource.endpoints}

    resources_by_version: dict[str, list[PlacedResource]] = {}
    for resource in resources:
        endpoints = [
            by_path[link.path] for link in resource.endpoints if link.path in by_path
        ]
        resources_by_version.setdefault(resource.api_version, []).append(
            PlacedResource(resource=resource, endpoints=_ordered(endpoints))
        )

    unassigned_by_version: dict[str, list[DocumentRecord]] = {}
    no_version: list[DocumentRecord] = []
    for document in documents:
        if document.path in placed_paths:
            continue
        if not has_api_version(document.api_version):
            no_version.append(document)
        else:
            unassigned_by_version.setdefault(document.api_version, []).append(document)

    versions = [
        LayoutVersion(
            api_version=api_version,
            resources=resources_by_version.get(api_version, []),
            unassigned=_ordered(unassigned_by_version.get(api_version, [])),
        )
        for api_version in sorted(
            resources_by_version.keys() | unassigned_by_version.keys()
        )
    ]
    return ServiceLayout(
        has_layout=True, versions=versions, no_version=_ordered(no_version)
    )


def start_layout(db: Session, service: Service, *, created_by: str) -> None:
    """Store the preliminary grouping of ``service``'s active Snapshot as its layout.

    The ``Layout`` row is flushed before anything is grouped. Its primary key is
    the service, so a second start - or one racing this one - fails right there
    with an ``IntegrityError``, and an existing layout stays as it is. Only the
    resources are stored; "unassigned" and "no version" are derived on read.

    Nothing is committed: the caller commits once, so a failure leaves no part
    of a layout behind and the start can be retried (ADR-0061).
    """
    db.add(Layout(service_id=service.id, created_by=created_by))
    db.flush()

    grouping = group_endpoints(db.scalars(_active_endpoints(service)).all())
    for version in grouping.versions:
        for grouped in version.resources:
            resource = Resource(
                service_id=service.id,
                api_version=version.api_version,
                name=grouped.name,
            )
            resource.endpoints = [
                ResourceEndpoint(service_id=service.id, path=path)
                for path in grouped.endpoints
            ]
            db.add(resource)
    db.flush()


def listed_versions(db: Session, service: Service) -> set[str]:
    """The API versions :func:`service_layout` lists, read from columns alone.

    The versions of the service's resources, and of the active Snapshot's
    endpoints that are in no resource and have a version - the "unassigned"
    ones. The same rule as the read, without loading a single payload, for an
    edit that needs only the names; which versions count is decided by
    :func:`has_api_version` in Python, as the read decides it, not restated in
    SQL.
    """
    resource_versions = set(
        db.scalars(
            select(Resource.api_version).where(Resource.service_id == service.id)
        )
    )
    placed = select(ResourceEndpoint.path).where(
        ResourceEndpoint.service_id == service.id
    )
    endpoint_versions = db.scalars(
        _active_endpoints(service)
        .with_only_columns(DocumentRecord.api_version)
        .distinct()
        .where(DocumentRecord.path.not_in(placed))
    )
    return resource_versions | {
        version for version in endpoint_versions if has_api_version(version)
    }


def active_endpoint(db: Session, service: Service, path: str) -> DocumentRecord | None:
    """The endpoint document at ``path`` in the service's active Snapshot, if any.

    What a layout edit may move: the same documents :func:`service_layout`
    shows, so an endpoint the read does not list cannot be placed either.
    """
    return db.scalar(_active_endpoints(service).where(DocumentRecord.path == path))


def unconfirm(resource: Resource) -> None:
    """Drop a resource's confirmation (ADR-0068); both columns go together."""
    resource.confirmed_by = None
    resource.confirmed_at = None


def switch_active_snapshot(db: Session, service: Service, snapshot_id: int) -> None:
    """Make ``snapshot_id`` the Snapshot ``service`` is served from.

    The one way to move ``active_snapshot_id``: a scan's ingest and an
    activation both go through here, so neither can move it and leave a
    confirmation behind that no longer covers its endpoints.

    The Service row is locked first - the lock the layout edits and the
    confirmation take - so no confirmation can be written between the check
    below and the move; a caller already holding it just keeps it.
    """
    db.execute(select(Service.id).where(Service.id == service.id).with_for_update())
    _drop_outdated_confirmations(db, service, snapshot_id)
    service.active_snapshot_id = snapshot_id


def _drop_outdated_confirmations(
    db: Session, service: Service, snapshot_id: int
) -> None:
    """Drop each confirmation ``snapshot_id`` would leave covering a different
    set of endpoints (ADR-0068) or an endpoint that is not ``ok`` (ADR-0067).

    A confirmation covers the name and the endpoints the user checked
    (ADR-0068): those of the resource in the active Snapshot, the ones the
    layout read shows. A rescan or an activation that takes one of them away,
    or brings back a stored path the confirmation never saw, leaves the
    resource with another set, so it has to be checked again - just as an edit
    that changes the set drops it.

    A resource is confirmed only while every endpoint it shows is ``ok``
    (ADR-0067), so one whose set stays still loses its confirmation when the
    new Snapshot reads any of them as not ``ok``. A resource whose set stays
    and is ``ok`` throughout keeps it.
    """
    if service.active_snapshot_id in (None, snapshot_id):
        return
    confirmed = db.scalars(
        select(Resource)
        .where(Resource.service_id == service.id, Resource.confirmed_by.is_not(None))
        .options(selectinload(Resource.endpoints))
    ).all()
    stored = {link.path for resource in confirmed for link in resource.endpoints}
    if not stored:
        return

    def shown_in(snapshot: int | None) -> dict[str, str | None]:
        rows = db.execute(
            select(DocumentRecord.path, DocumentRecord.overall_status).where(
                DocumentRecord.snapshot_id == snapshot,
                DocumentRecord.kind == ENDPOINT_KIND,
                DocumentRecord.path.in_(stored),
            )
        ).all()
        return {path: status for path, status in rows}

    before, after = shown_in(service.active_snapshot_id), shown_in(snapshot_id)
    for resource in confirmed:
        mine = {link.path for link in resource.endpoints}
        kept = mine & after.keys()
        if kept != mine & before.keys():
            reason = "changes its endpoints"
        elif any(after[path] != OverallStatus.OK for path in kept):
            reason = "leaves an endpoint not ok"
        else:
            continue
        unconfirm(resource)
        logger.info(
            "service %s: confirmation of resource %s dropped, snapshot %s %s",
            service.repo,
            resource.id,
            snapshot_id,
            reason,
        )


def endpoint_statuses(
    db: Session, service: Service, resource: Resource
) -> dict[str, str | None]:
    """The endpoints of ``resource`` in the active Snapshot, with their status.

    Path to ``overall_status``: the endpoints :func:`service_layout` shows in
    the resource, and only those - a stored path the active Snapshot lacks is
    not shown, so nothing about it can be checked or confirmed.
    """
    placed = select(ResourceEndpoint.path).where(
        ResourceEndpoint.service_id == service.id,
        ResourceEndpoint.resource_id == resource.id,
    )
    rows = db.execute(
        _active_endpoints(service)
        .with_only_columns(DocumentRecord.path, DocumentRecord.overall_status)
        .where(DocumentRecord.path.in_(placed))
    ).all()
    return {path: status for path, status in rows}


def _active_endpoints(service: Service) -> Select[tuple[DocumentRecord]]:
    return select(DocumentRecord).where(
        DocumentRecord.snapshot_id == service.active_snapshot_id,
        DocumentRecord.kind == ENDPOINT_KIND,
    )


def _ordered(documents: Iterable[DocumentRecord]) -> list[DocumentRecord]:
    return sorted(
        documents,
        key=lambda document: (document.uri or "", document.method or "", document.path),
    )
