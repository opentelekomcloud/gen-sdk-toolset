"""Propose SDK methods for the endpoints bound to one layout resource (ISS-0075)."""

from __future__ import annotations

import keyword
import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from pydantic.alias_generators import to_snake

from tools.panel.core.action_selectors import (
    ACTION,
    ActionSelector,
    action_selectors,
    is_command,
)
from tools.panel.core.grouping import uri_segments
from tools.shared.ir import Endpoint, HttpMethod


class OperationKind(StrEnum):
    get = "get"
    list = "list"
    create = "create"
    update = "update"
    delete = "delete"
    non_standard = "non-standard"


class NamingConflict(StrEnum):
    missing_action_selector = "missing_action_selector"
    ambiguous_action_selector = "ambiguous_action_selector"
    missing_name = "missing_name"
    duplicate_name = "duplicate_name"


@dataclass(frozen=True)
class SpecOperation:
    """One SDK method proposal per source operation or documented action variant.

    TODO(ISS-0076): attach the source endpoint and expose it on the spec page.
    """

    path: str
    kind: OperationKind
    proposed_name: str | None
    selector: ActionSelector | None = None
    conflict: NamingConflict | None = None


def _identifier(parts: tuple[str, ...]) -> str | None:
    words = [re.sub("[^a-z0-9]+", "_", to_snake(part)).strip("_") for part in parts]
    name = "_".join(filter(None, words))
    if not name:
        return None
    if name[0].isdigit():
        name = "op_" + name
    return name + "_" if keyword.iskeyword(name) else name


def _kind(method: HttpMethod, segments: tuple[str | None, ...]) -> OperationKind:
    literals = tuple(s for s in segments if s is not None)
    on_item = segments[-1:] == (None,)
    leaf = literals[-1] if literals else ""
    if method is HttpMethod.GET and leaf == "detail" and not on_item:
        return OperationKind.get if segments[-2:-1] == (None,) else OperationKind.list
    plural = leaf.lower().endswith("s") and not leaf.lower().endswith(("ss", "us"))
    if (
        not on_item
        and is_command(leaf)
        and (method is not HttpMethod.GET or not plural)
    ):
        return OperationKind.non_standard
    collection = not on_item and (len(literals) <= 1 or plural)
    match method:
        case HttpMethod.GET:
            return OperationKind.list if collection else OperationKind.get
        case HttpMethod.POST if collection:
            return OperationKind.create
        case HttpMethod.PUT | HttpMethod.PATCH:
            return OperationKind.update
        case HttpMethod.DELETE:
            return OperationKind.delete
        case _:
            return OperationKind.non_standard


def _action_operations(
    endpoints: list[Endpoint], collection: str | None
) -> Iterator[SpecOperation]:
    for endpoint, selectors, ambiguous in action_selectors(endpoints):
        for selector in sorted(
            selectors, key=lambda s: (s.keys, s.value or "", s.section)
        ):
            name = _identifier(selector.name_parts(collection))
            yield SpecOperation(
                endpoint.path,
                OperationKind.non_standard,
                name,
                selector,
                None if name else NamingConflict.missing_name,
            )
        if ambiguous or not selectors:
            reason = (
                NamingConflict.ambiguous_action_selector
                if ambiguous
                else NamingConflict.missing_action_selector
            )
            yield SpecOperation(
                endpoint.path, OperationKind.non_standard, None, conflict=reason
            )


def _ordinary_name(
    kind: OperationKind, literals: tuple[str, ...], *, include_root: bool
) -> str | None:
    nested = literals if include_root else literals[1:]
    parts = (
        (nested or literals)
        if kind is OperationKind.non_standard
        else (kind.value, *nested)
    )
    return _identifier(parts)


def propose_operations(endpoints: Sequence[Endpoint]) -> list[SpecOperation]:
    """Propose names for all endpoints assigned to one resource in the layout."""
    operations: list[SpecOperation] = []
    actions: defaultdict[tuple[HttpMethod, tuple[str | None, ...]], list[Endpoint]] = (
        defaultdict(list)
    )
    qualified_names: dict[str, str] = {}
    alternatives: defaultdict[str, set[str]] = defaultdict(set)
    for endpoint in endpoints:
        segments = uri_segments(endpoint.uri)
        literals = tuple(s for s in segments if s is not None)
        if segments[-1:] == (ACTION,):
            actions[endpoint.method, segments].append(endpoint)
        else:
            kind = _kind(endpoint.method, segments)
            name = _ordinary_name(kind, literals, include_root=False)
            conflict = None if name else NamingConflict.missing_name
            operations.append(
                SpecOperation(endpoint.path, kind, name, conflict=conflict)
            )
            qualified = _ordinary_name(kind, literals, include_root=True)
            if name and qualified:
                alternatives[name].add(qualified)
                qualified_names[endpoint.path] = qualified
    for (_, segments), group in actions.items():
        collection = next((s for s in reversed(segments[:-1]) if s is not None), None)
        operations.extend(_action_operations(group, collection))
    # Manual layout moves can put different URI roots in the same resource.
    operations = [
        replace(op, proposed_name=qualified_names[op.path])
        if op.selector is None
        and op.proposed_name
        and len(alternatives[op.proposed_name]) > 1
        else op
        for op in operations
    ]
    operations.sort(key=lambda op: op.path)
    counts = Counter(op.proposed_name for op in operations if op.proposed_name)
    return [
        replace(op, conflict=NamingConflict.duplicate_name)
        if op.proposed_name and counts[op.proposed_name] > 1
        else op
        for op in operations
    ]
