"""Model text -> data -> schema check. Truncated JSON is not repaired.

``parse_object`` is the one place that turns model text into a JSON object: the
service uses it through ``Parser``, a caller that asks for raw text (no schema)
uses it directly. Two parsers with two ideas of tolerance is how answers start
to pass in one place and fail in another.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Validator = Callable[[dict[str, Any], dict[str, Any]], None]

#: Default: find a validator; ``validator=None`` means there is deliberately none.
AUTO: Any = object()


@dataclass(frozen=True)
class Parsed:
    data: dict[str, Any] | None = None
    failure: str = ""
    error: str = ""


def parse_object(text: str) -> Parsed:
    """Text from a model -> exactly one JSON object.

    Strips a ```-fence and chatter around a complete object; never completes a
    truncated one - an object finished on the model's behalf is an invention.
    """
    payload = _loads(_unfence(text))
    if payload is None:
        return Parsed(
            failure="invalid_json", error=f"could not parse: {_preview(text)}"
        )
    if not isinstance(payload, dict):
        return Parsed(
            failure="invalid_json",
            error=f"top level is {type(payload).__name__}, not an object",
        )
    return Parsed(data=payload)


class Parser:
    def __init__(self, validator: Validator | None | Any = AUTO) -> None:
        self._validator = jsonschema_validator() if validator is AUTO else validator

    def parse_and_validate(self, text: str, schema: dict[str, Any] | None) -> Parsed:
        parsed = parse_object(text)
        if parsed.failure or schema is None:
            return parsed
        # Fail closed: a schema was asked for and cannot be checked.
        if self._validator is None:
            return Parsed(
                data=parsed.data,
                failure="config",
                error="schema validation is unavailable: jsonschema is not installed",
            )
        try:
            self._validator(parsed.data or {}, schema)
        except Exception as error:  # the validator raises its own type
            return Parsed(
                data=parsed.data,
                failure="schema_invalid",
                error=f"{type(error).__name__}: {error}",
            )
        return parsed


def jsonschema_validator() -> Validator | None:
    try:
        import jsonschema
    except ImportError:
        return None

    def validate(data: dict[str, Any], schema: dict[str, Any]) -> None:
        jsonschema.validate(data, schema)

    return validate


def _unfence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    newline = body.find("\n")
    if newline != -1:
        body = body[newline + 1 :]
    closing = body.rfind("```")
    if closing != -1:
        body = body[:closing]
    return body.strip()


def _loads(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Chatter around a complete object; a truncated object still fails, and that
    # is intended.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        return None


def _preview(text: str, limit: int = 200) -> str:
    text = (text or "").strip()
    return text[:limit] + ("…" if len(text) > limit else "")
