"""The preliminary grouping of a service's endpoints into resources.

A starting point the user corrects by hand, not a decision: every endpoint of
the active snapshot is placed, whatever its status (ADR-0058), and one the rule
cannot place gets no invented name - it waits in a list of its own. An endpoint
with no API version goes to "no version" (ADR-0059); one whose URI has no
constant segment after the version goes to its version's "unassigned" list
(ADR-0057). The rest go into resources named after that segment.

Pure: no I/O and no database. It reads only a document's kind, path, URI and
API version - fields the IR ``Endpoint`` has and ``DocumentRecord`` projects
as columns - so a caller can group rows without deserializing their payloads.
It reads the URI with the scanner's own patterns - its version and placeholder
patterns - so it lives here rather than in :mod:`tools.panel.core.analytics`,
which may not import the scanner. Placeholders are found before the URI is
split, and each segment's percent-encoding is undone only after it is split
off, so ``%7Bid%7D`` is a parameter too and ``%2F`` never splits a segment.
"""

from __future__ import annotations

import re
import string
import urllib.parse
from collections import defaultdict
from collections.abc import Sequence
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tools.scanner.parsers.docutils.patterns import API_VERSION_RE, URI_PLACEHOLDER_RE
from tools.shared.exceptions import GenSdkError
from tools.shared.ir import ENDPOINT_KIND

#: A valid resource name (ADR-0065): a resource becomes the Python package
#: ``services/<service>/<version>/<resource>/``, so the name must be one.
RESOURCE_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"

#: Put in front of a name that does not start with a letter (ADR-0057).
RESOURCE_NAME_PREFIX = "r_"

_INVALID_NAME_CHAR_RE = re.compile(r"[^a-z0-9_]")

#: Stands in for each path parameter while the URI is split into segments, so a
#: parameter whose name holds a ``/`` stays one segment. A URI as written cannot
#: hold it, and it is looked for before a segment is decoded, so ``%00`` cannot
#: pass for it either.
_PARAMETER = "\0"

#: What a decoded segment still holds only if a placeholder in it is broken or
#: encoded - ``{}``, a stray brace, ``%7Bid%7D``: a parameter all the same,
#: never a name.
_BROKEN_PARAMETER = frozenset("{}")

_VERSION_NUMBER_RE = re.compile(r"\d+")


class NotAnEndpointError(GenSdkError):
    """A document that is not an endpoint was passed to :func:`group_endpoints`.

    A caller error - the rows were not filtered by kind - kept apart from the
    ``ValidationError`` a broken grouping invariant raises.
    """


class GroupableEndpoint(Protocol):
    """What the rule reads of an endpoint document.

    The IR ``Endpoint`` and a ``DocumentRecord`` row both qualify. ``kind``
    is read so that a row of another kind is refused rather than shown as an
    endpoint. A row's URI is nullable; an endpoint without one has no segment
    to name a resource after.
    """

    @property
    def kind(self) -> str: ...

    @property
    def path(self) -> str: ...

    @property
    def uri(self) -> str | None: ...

    @property
    def api_version(self) -> str | None: ...


class GroupedResource(BaseModel):
    """Endpoints of one API version whose URIs give the same name.

    What the rule proposes, not the stored ``Resource`` row of a layout
    (:mod:`tools.panel.core.db.models`) - the two meet when the grouping is
    saved, so they do not share a name.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=RESOURCE_NAME_PATTERN)
    #: Document paths, the endpoints' identity within a snapshot.
    endpoints: list[str] = Field(min_length=1)


class VersionGroup(BaseModel):
    """What the rule made of the endpoints of one API version."""

    model_config = ConfigDict(extra="forbid")

    api_version: str = Field(min_length=1)
    resources: list[GroupedResource] = Field(default_factory=list)
    #: Endpoints whose URI has no constant segment after the version, or no URI.
    unassigned: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contents(self) -> Self:
        # the rule makes a group only for a version it saw an endpoint of
        if not self.resources and not self.unassigned:
            raise ValueError(f"version group {self.api_version} holds no endpoint")
        names = [resource.name for resource in self.resources]
        if len(names) != len(set(names)):
            raise ValueError(f"resource names must be unique within {self.api_version}")
        return self


class EndpointGrouping(BaseModel):
    """The preliminary grouping of every endpoint of one snapshot.

    Each endpoint is in exactly one place - a resource, an "unassigned" list or
    "no version" - so the editor shows everything the scanner found, once.
    """

    model_config = ConfigDict(extra="forbid")

    versions: list[VersionGroup] = Field(default_factory=list)
    #: Endpoints the scanner found no API version for, or an empty one.
    no_version: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_placement(self) -> Self:
        versions = [group.api_version for group in self.versions]
        if len(versions) != len(set(versions)):
            raise ValueError("each API version must be grouped once")
        placed = [
            *self.no_version,
            *(
                path
                for group in self.versions
                for path in [
                    *group.unassigned,
                    *(p for r in group.resources for p in r.endpoints),
                ]
            ),
        ]
        if len(placed) != len(set(placed)):
            raise ValueError("an endpoint must be placed exactly once")
        return self


def group_endpoints(endpoints: Sequence[GroupableEndpoint]) -> EndpointGrouping:
    """Group a snapshot's endpoints into resources, per API version.

    Every list is sorted - versions by number (``v2`` before ``v10``), resource
    names and paths by text - so the result does not depend on the order the
    endpoints were read in.

    Raises :class:`NotAnEndpointError` for a document that is not an endpoint:
    the caller passed the wrong rows, and placing them would show pages as
    endpoints. Raises pydantic's ``ValidationError`` - a ``ValueError`` - when
    the result breaks an invariant of :class:`EndpointGrouping`, such as two
    endpoints with one path, which one snapshot cannot hold.
    """
    no_version: list[str] = []
    unassigned: defaultdict[str, list[str]] = defaultdict(list)
    resources: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for endpoint in endpoints:
        if endpoint.kind != ENDPOINT_KIND:
            raise NotAnEndpointError(
                f"{endpoint.path} is a {endpoint.kind!r} document, not an endpoint"
            )
        version = endpoint.api_version
        # an empty version names no version either: it would be a group with no name
        if not version:
            no_version.append(endpoint.path)
            continue
        segment = _resource_segment(endpoint.uri)
        if segment is None:
            unassigned[version].append(endpoint.path)
        else:
            resources[version][_resource_name(segment)].append(endpoint.path)

    return EndpointGrouping(
        versions=[
            VersionGroup(
                api_version=version,
                resources=[
                    GroupedResource(name=name, endpoints=sorted(paths))
                    for name, paths in sorted(resources[version].items())
                ],
                unassigned=sorted(unassigned[version]),
            )
            for version in sorted(
                resources.keys() | unassigned.keys(), key=_version_order
            )
        ],
        no_version=sorted(no_version),
    )


def _version_order(version: str) -> tuple[list[int], str]:
    numbers = [int(n) for n in _VERSION_NUMBER_RE.findall(version)]
    return numbers, version


def _resource_segment(uri: str | None) -> str | None:
    if uri is None:
        return None
    # Read as written: placeholders, the query string, the version segment and
    # the "/" between segments are all found before anything is decoded, so
    # "%3F" and "%2F" stay inside their segment.
    path = URI_PLACEHOLDER_RE.sub(_PARAMETER, uri).split("?", 1)[0]
    version = API_VERSION_RE.search(path)
    after_version = path[version.end(1) :] if version else path
    for raw in after_version.split("/"):
        if not raw or _PARAMETER in raw:
            continue
        segment = urllib.parse.unquote(raw)
        if _BROKEN_PARAMETER.isdisjoint(segment):
            return segment
    return None


def _resource_name(segment: str) -> str:
    name = _INVALID_NAME_CHAR_RE.sub("_", segment.lower())
    if name[0] not in string.ascii_lowercase:
        name = RESOURCE_NAME_PREFIX + name
    return name
