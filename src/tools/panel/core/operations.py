"""Propose the default kind and SDK method name of each operation (ISS-0090)."""

from __future__ import annotations

import keyword
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic.alias_generators import to_snake

from tools.panel.core.grouping import uri_segments
from tools.shared.ir import Endpoint, HttpMethod


class OperationKind(StrEnum):
    get = "get"
    list = "list"
    create = "create"
    update = "update"
    delete = "delete"
    custom = "custom"


_ITEM_KINDS = {
    HttpMethod.GET: OperationKind.get,
    HttpMethod.PUT: OperationKind.update,
    HttpMethod.PATCH: OperationKind.update,
    HttpMethod.DELETE: OperationKind.delete,
}
_COLLECTION_KINDS = {
    HttpMethod.GET: OperationKind.list,
    HttpMethod.POST: OperationKind.create,
}


class MissingName(StrEnum):
    """Why the rule proposes no name for an operation (ADR-0120)."""

    same_call = "same_call"
    name_conflict = "name_conflict"
    no_segment = "no_segment"


@dataclass(frozen=True)
class SpecOperation:
    """One operation per source document, with its default kind and name.

    ``name`` is None exactly when ``missing_name`` says why.
    TODO(ISS-0091): attach the source endpoint and expose it on the spec page.
    """

    path: str
    kind: OperationKind
    name: str | None
    missing_name: MissingName | None = None


def _identifier(parts: tuple[str, ...]) -> str | None:
    words = [re.sub("[^a-z0-9]+", "_", to_snake(part)).strip("_") for part in parts]
    name = "_".join(filter(None, words))
    if not name:
        return None
    if name[0].isdigit():
        name = "op_" + name
    return name + "_" if keyword.iskeyword(name) else name


def _singular(word: str) -> str:
    lower = word.lower()
    if lower.endswith("ies"):
        return word[:-3] + "y"
    if lower.endswith(("sses", "xes", "shes")):
        return word[:-2]
    if lower.endswith("s") and not lower.endswith(("ss", "us", "sis")):
        return word[:-1]
    return word


def _collections(
    all_segments: Sequence[tuple[str | None, ...]],
) -> set[tuple[str | None, ...]]:
    """Prefixes ending in a constant segment that some URI follows with a parameter."""
    return {
        segments[:i]
        for segments in all_segments
        for i in range(1, len(segments))
        if segments[i] is None and segments[i - 1] is not None
    }


def _kind(
    method: HttpMethod,
    segments: tuple[str | None, ...],
    collections: set[tuple[str | None, ...]],
) -> OperationKind:
    if segments[-1:] == (None,):
        if segments[:-1] in collections:
            return _ITEM_KINDS.get(method, OperationKind.custom)
        return OperationKind.custom
    if segments in collections:
        return _COLLECTION_KINDS.get(method, OperationKind.custom)
    return OperationKind.custom


def _name(kind: OperationKind, segments: tuple[str | None, ...]) -> str | None:
    literals = tuple(s for s in segments if s is not None)
    nested = literals[1:]
    if kind is OperationKind.custom:
        return _identifier(nested or literals)
    if nested and kind is not OperationKind.list:
        nested = (*nested[:-1], _singular(nested[-1]))
    return _identifier((kind.value, *nested))


def propose_operations(endpoints: Sequence[Endpoint]) -> list[SpecOperation]:
    """Propose the kind and name of every endpoint assigned to one layout resource."""
    segments = {e.path: uri_segments(e.uri) for e in endpoints}
    methods = {e.path: e.method for e in endpoints}
    collections = _collections(list(segments.values()))
    kinds = {e.path: _kind(e.method, segments[e.path], collections) for e in endpoints}
    names = {path: _name(kinds[path], segments[path]) for path in segments}
    missing = {path: MissingName.no_segment for path in names if names[path] is None}

    # Documents of one HTTP method and URI: only the user can tell them apart.
    same_call: defaultdict[tuple[HttpMethod, str], list[str]] = defaultdict(list)
    for endpoint in endpoints:
        uri = endpoint.uri.split("?", 1)[0].rstrip("/")
        same_call[endpoint.method, uri].append(endpoint.path)
    for paths in same_call.values():
        if len(paths) > 1:
            for path in paths:
                names[path], missing[path] = None, MissingName.same_call

    for paths in _same_name(names):
        several_methods = len({methods[path] for path in paths}) > 1
        has_base = any(kinds[path] is not OperationKind.custom for path in paths)
        for path in paths:
            method, name = methods[path], names[path]
            if kinds[path] is OperationKind.custom:
                if several_methods or has_base:
                    names[path] = f"{method.value.lower()}_{name}"
            elif several_methods and method is HttpMethod.PATCH:
                names[path] = "patch" + name.removeprefix(OperationKind.update.value)
    for paths in _same_name(names):
        for path in paths:
            names[path], missing[path] = None, MissingName.name_conflict

    return [
        SpecOperation(path, kinds[path], names[path], missing.get(path))
        for path in sorted(segments)
    ]


def _same_name(names: dict[str, str | None]) -> list[list[str]]:
    counts = Counter(name for name in names.values() if name)
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for path, name in names.items():
        if name and counts[name] > 1:
            groups[name].append(path)
    return list(groups.values())
