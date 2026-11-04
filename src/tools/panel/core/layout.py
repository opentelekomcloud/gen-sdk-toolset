"""A service's layout: which of its endpoints form which resource.

Stored resources are matched to the active Snapshot's endpoint documents by
path; a path that Snapshot lacks is left out. The "unassigned" and "no version"
lists are derived here, never stored, so they follow the active Snapshot.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, undefer

from tools.panel.core.db.models import DocumentRecord, Layout, Resource, Service
from tools.shared.ir import Endpoint

_ENDPOINT_KIND = Endpoint.model_fields["kind"].default


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
        select(DocumentRecord)
        .where(
            DocumentRecord.snapshot_id == service.active_snapshot_id,
            DocumentRecord.kind == _ENDPOINT_KIND,
        )
        .options(undefer(DocumentRecord.payload))
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


def _ordered(documents: Iterable[DocumentRecord]) -> list[DocumentRecord]:
    return sorted(
        documents,
        key=lambda document: (document.uri or "", document.method or "", document.path),
    )
