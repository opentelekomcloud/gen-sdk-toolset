"""Response schemas by id. The root is given explicitly, never discovered."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SchemaNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Schema:
    id: str
    body: dict[str, Any]
    sha: str


class SchemaRepository:
    def __init__(self, root: Path | str, *, suffix: str = ".schema.json") -> None:
        self.root = Path(root)
        self._suffix = suffix
        self._loaded: dict[str, Schema] = {}
        self._lock = threading.Lock()

    def get(self, schema_id: str) -> Schema:
        with self._lock:
            found = self._loaded.get(schema_id)
            if found is not None:
                return found
        schema = self._load(schema_id)
        with self._lock:
            self._loaded.setdefault(schema_id, schema)
            return self._loaded[schema_id]

    def _load(self, schema_id: str) -> Schema:
        if not schema_id or "/" in schema_id or "\\" in schema_id or ".." in schema_id:
            raise SchemaNotFound(f"bad schema id: {schema_id!r}")
        path = self.root / f"{schema_id}{self._suffix}"
        try:
            # UnicodeDecodeError is a ValueError, NaN/Infinity are refused at parse,
            # and sha_of can raise on values json.dumps will not serialise.
            text = path.read_text(encoding="utf-8")
            body = json.loads(text, parse_constant=_refuse_constant)
            if not isinstance(body, dict):
                raise ValueError("schema is not an object")
            return Schema(id=schema_id, body=body, sha=sha_of(body))
        except (OSError, ValueError) as error:
            raise SchemaNotFound(f"{schema_id}: {path} - {error}") from error


def _refuse_constant(name: str) -> float:
    raise ValueError(f"{name} is not valid JSON for a schema")


def sha_of(body: dict[str, Any]) -> str:
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
