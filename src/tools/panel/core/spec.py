"""The specification of one resource: what the Python SDK will make of it.

Built on every request from the current layout and the active Snapshot's
documents, never stored, so a rescan, an activation, a layout edit or a CLI
write shows at once (ADR-0115). The generation job builds its model with the
same function (ADR-0114).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from tools.panel.core.db.models import Service
from tools.panel.core.layout import PlacedResource, service_layout


@dataclass(frozen=True)
class SpecOperation:
    """One operation of the resource. TODO(ISS-0076): its kind, method and endpoint."""


@dataclass(frozen=True)
class SpecClass:
    """One class of the resource. TODO(ISS-0077): its fields, names and types."""


@dataclass(frozen=True)
class ResourceSpec:
    """The two sections of a resource's specification (ADR-0088)."""

    operations: list[SpecOperation]
    classes: list[SpecClass]


def resource_spec(
    db: Session, service: Service, resource_id: int
) -> ResourceSpec | None:
    """Build the specification of ``service``'s resource ``resource_id``.

    None if the service's layout has no such resource.
    """
    placed = _find_resource(db, service, resource_id)
    if placed is None:
        return None
    return ResourceSpec(operations=[], classes=[])


def _find_resource(
    db: Session, service: Service, resource_id: int
) -> PlacedResource | None:
    for version in service_layout(db, service).versions:
        for placed in version.resources:
            if placed.resource.id == resource_id:
                return placed
    return None
