"""A service's layout: which of its endpoints form which resource.

Stored resources are matched to the active Snapshot's endpoint documents by
path; a path that Snapshot lacks is left out. The "unassigned" and "no version"
lists are derived here, never stored, so they follow the active Snapshot.

A layout is created once, by the preliminary grouping (:func:`start_layout`);
after that it changes only by editing (ADR-0072).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload, undefer

from tools.panel.core.db.models import (
    DocumentRecord,
    Layout,
    Resource,
    ResourceEndpoint,
    Service,
)
from tools.panel.core.grouping import group_endpoints
from tools.shared.ir import ENDPOINT_KIND


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
        if document.api_version is None:
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
