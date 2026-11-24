"""The specification of one resource: what the Python SDK will make of it.

Built on every request from the current layout and the active Snapshot's
documents, never stored, so a rescan, an activation, a layout edit or a CLI
write shows at once (ADR-0115). The generation job builds its model with the
same function (ADR-0114).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tools.panel.core.db.models import Resource, Service
from tools.panel.core.layout import resource_endpoints
from tools.panel.core.operations import SpecOperation, propose_operations


@dataclass(frozen=True)
class SpecClass:
    """One class of the resource. TODO(ISS-0092): its fields, names and types."""


@dataclass(frozen=True)
class ResourceSpec:
    """A resource and the two sections of its specification (ADR-0088)."""

    name: str
    confirmed: bool
    operations: list[SpecOperation]
    classes: list[SpecClass]


def resource_spec(
    db: Session, service: Service, api_version: str, resource_id: int
) -> ResourceSpec | None:
    """Build the specification of ``service``'s resource ``resource_id``.

    None if the service's layout has no such resource in ``api_version``.
    """
    resource = db.scalar(
        select(Resource).where(
            Resource.service_id == service.id,
            Resource.api_version == api_version,
            Resource.id == resource_id,
        )
    )
    if resource is None:
        return None
    endpoints = resource_endpoints(db, service, resource)
    proposed = {op.path: op for op in propose_operations(endpoints)}
    return ResourceSpec(
        name=resource.name,
        confirmed=resource.confirmed_by is not None,
        operations=[proposed[e.path] for e in endpoints],
        classes=[],
    )
