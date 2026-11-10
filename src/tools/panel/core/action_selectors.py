"""Read the request evidence that distinguishes operations on an /action URI."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl

from pydantic.alias_generators import to_snake

from tools.scanner.parsers.docutils.patterns import URI_PLACEHOLDER_RE
from tools.shared.ir import (
    Endpoint,
    Example,
    HttpMethod,
    Parameter,
    ParameterType,
    SectionName,
)

ACTION = "action"

COMMAND_WORDS = frozenset(
    """access add apply associate attach batch bind cancel change check close
    confirm copy count create delete deny detach disable disassociate enable
    enlarge execute expand export extend failover filter get import list lock
    migrate monitor open protect publish query reboot rebuild recover remove
    reserve reset resize restart restore resume reverse revert revoke scale
    search set shrink start stop switch unbind unlock unreserve update upgrade
    validate""".split()
)

_TOKEN = r"[A-Za-z][A-Za-z0-9_-]*"


@dataclass(frozen=True)
class ActionSelector:
    """Exact request keys and optional field value, before SDK normalization."""

    keys: tuple[str, ...]
    value: str | None = None
    section: SectionName = SectionName.BODY

    def name_parts(self, collection: str | None) -> tuple[str, ...]:
        if self.value is not None:
            return (self.value, collection) if collection else (self.value,)
        if len(self.keys) == 1:
            return (self.keys[0].removeprefix("os-"),)
        if is_command(self.keys[-2]) and not is_command(self.keys[-1]):
            return self.keys[-2:]
        return (self.keys[-1], self.keys[-2])


def is_command(word: str) -> bool:
    return to_snake(word.removeprefix("os-")).split("_", 1)[0] in COMMAND_WORDS


def _documented_values(description: str) -> set[str]:
    """Read scoped instructions before a table's general list of allowed values."""
    specific = re.findall(rf"\bUse ({_TOKEN}) to\b", description)
    if specific:
        return set(specific)
    lines = description.splitlines()
    for index, line in enumerate(lines):
        if line.strip() in {"Enumeration values:", "Range"}:
            values = set()
            for item in lines[index + 1 :]:
                if item.strip():
                    if not re.fullmatch(_TOKEN, item.strip()):
                        break
                    values.add(item.strip())
            if values:
                return values
    labelled = re.findall(rf"^({_TOKEN}):[ \t]+\S", description, re.MULTILINE)
    if labelled:
        return set(labelled)
    conditional = re.findall(
        rf"\bif (?:action(?:-id)?|the value) is set to ({_TOKEN})\b", description, re.I
    )
    if conditional:
        return set(conditional)
    choices = re.search(
        rf"\b(?:values are|value is|can (?:only )?be(?: set to)?) "
        rf"({_TOKEN}(?:(?:,\s*(?:(?:or|and) )?| (?:or|and) ){_TOKEN})+)"
        rf"(?= only\b|[.]|$)",
        description,
        re.IGNORECASE,
    )
    return (
        set(re.split(r",\s*(?:(?:or|and) )?| (?:or|and) ", choices[1]))
        if choices
        else set()
    )


def _root_parameters(parameters: list[Parameter]) -> dict[str, Parameter]:
    # A scanner table can also project nested fields as flat rows.
    children = {child.name for p in parameters for child in p.children}
    return {p.name: p for p in parameters if p.name not in children}


def _schema_envelopes(roots: dict[str, Parameter]) -> list[tuple[str, ...]]:
    keys = []
    parameters = list(roots.values())
    while len(parameters) == 1:
        [field] = parameters
        if field.children or field.param_type in (
            ParameterType.OBJECT,
            ParameterType.ARRAY,
        ):
            keys.append(field.name)
        elif not keys and (is_command(field.name) or field.name.startswith("os-")):
            keys.append(field.name)
        else:
            break
        if field.param_type is ParameterType.ARRAY:
            break
        parameters = field.children
    if len(parameters) > 1 and all(
        not field.mandatory
        and is_command(field.name)
        and (
            field.children
            or field.param_type in (ParameterType.OBJECT, ParameterType.ARRAY)
        )
        for field in parameters
    ):
        return [(*keys, field.name) for field in parameters]
    return [tuple(keys)] if keys else []


def _envelope(body: dict) -> tuple[str, ...]:
    keys = []
    while isinstance(body, dict) and len(body) == 1:
        key, body = next(iter(body.items()))
        if body is not None and not isinstance(body, (list, dict)):
            if not keys and is_command(key):
                keys.append(key)
            break
        keys.append(key)
    return tuple(keys)


@dataclass
class _Evidence:
    envelopes: set[tuple[str, ...]]
    selectors: set[ActionSelector]
    ambiguous: bool


def _request_bodies(
    examples: list[Example], method: HttpMethod
) -> Iterable[dict | None]:
    """Read old snapshot examples with several versioned URLs before one JSON body."""
    for example in examples:
        body = example.parsed
        if body is None:
            raw = example.raw.strip()
            while raw:
                first, _, rest = raw.partition("\n")
                url = first.strip().removeprefix(method.value + " ").strip()
                if not re.fullmatch(
                    r"(?:https?://|/)\S+", URI_PLACEHOLDER_RE.sub("param", url)
                ):
                    break
                raw = rest.lstrip()
            if not raw:
                continue
            try:
                body = json.loads(raw)
            except (ValueError, RecursionError):
                pass
        yield body if isinstance(body, dict) else None


def _request_evidence(endpoint: Endpoint) -> _Evidence:
    sections = {section.name: section for section in endpoint.sections}
    roots = _root_parameters(sections[SectionName.BODY].parameters)
    action_field = roots.get(ACTION)
    query_fields = {
        p.name: _documented_values(p.description)
        for p in sections[SectionName.QUERY_PARAMS].parameters
        if p.name in {ACTION, "action-id"}
    }
    fixed_query: defaultdict[str, set[str]] = defaultdict(set)
    for key, value in parse_qsl(endpoint.uri.partition("?")[2]):
        if key in {ACTION, "action-id"} and re.fullmatch(_TOKEN, value):
            fixed_query[key].add(value)
    query_fields.update(fixed_query)
    query_selectors = {
        ActionSelector((key,), value, SectionName.QUERY_PARAMS)
        for key, values in query_fields.items()
        for value in values
    }
    bodies = list(
        _request_bodies(sections[SectionName.EXAMPLE_REQUEST].examples, endpoint.method)
    )
    if (
        query_fields
        and not action_field
        and not any(obj and ACTION in obj for obj in bodies)
    ):
        return _Evidence(set(), query_selectors, not all(query_fields.values()))
    values = _documented_values(action_field.description) if action_field else set()
    envelopes = set()
    ambiguous = False
    for obj in bodies:
        if obj is None:
            ambiguous = True
            continue
        if ACTION in obj:
            value = obj[ACTION]
            if isinstance(value, str) and re.fullmatch(_TOKEN, value):
                values.add(value)
            else:
                ambiguous = True
            continue
        if roots and not roots.keys() & obj.keys():
            # Some request-example sections include an API error response.
            if len(obj) == 1 and any(
                isinstance(payload, dict) and {"message", "code"} <= payload.keys()
                for payload in obj.values()
            ):
                continue
        path = _envelope(obj)
        if path:
            envelopes.add(path)
        else:
            ambiguous = True
    if not action_field:
        for schema_path in _schema_envelopes(roots):
            if not any(p[: len(schema_path)] == schema_path for p in envelopes):
                envelopes.add(schema_path)
    if action_field:
        ambiguous |= not values and bool(envelopes)
    elif roots and not envelopes and not values:
        ambiguous = True
    selectors = {ActionSelector((ACTION,), value) for value in values}
    return _Evidence(
        envelopes, selectors | query_selectors, ambiguous or bool(query_fields)
    )


def _selector(
    path: tuple[str, ...], branches: set[tuple[str, ...]]
) -> ActionSelector | None:
    """Use the deepest branching key to distinguish actions under a shared command."""
    command_depth = next(
        (
            i
            for i, key in enumerate(path, 1)
            if is_command(key) or key.startswith("os-") or key == "single_to_ha"
        ),
        0,
    )
    for depth in range(len(path), command_depth, -1):
        if path[: depth - 1] in branches:
            return ActionSelector(path[:depth])
    if command_depth:
        return ActionSelector(path[:command_depth])
    if len(path) == 1:
        return ActionSelector(path)
    return None


def action_selectors(
    endpoints: Sequence[Endpoint],
) -> Iterable[tuple[Endpoint, set[ActionSelector], bool]]:
    """Resolve documented alternative envelopes on one HTTP method and URI."""
    evidence = [_request_evidence(endpoint) for endpoint in endpoints]
    children: defaultdict[tuple[str, ...], set[str]] = defaultdict(set)
    for item in evidence:
        for path in item.envelopes:
            for index, key in enumerate(path):
                children[path[:index]].add(key)
    branches = {prefix for prefix, keys in children.items() if len(keys) > 1}
    for endpoint, item in zip(endpoints, evidence, strict=True):
        selectors = item.selectors.copy()
        ambiguous = item.ambiguous
        for path in item.envelopes:
            selector = _selector(path, branches)
            if selector is None:
                ambiguous = True
            else:
                selectors.add(selector)
        yield endpoint, selectors, ambiguous
