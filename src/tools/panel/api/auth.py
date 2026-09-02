"""Bearer-token authentication for the panel API, against Zitadel.

Every request outside ``/health`` carries an OIDC access token; this module is
where it is checked and turned into an :class:`Identity`. Two roles exist:
``worker`` may change panel state, ``viewer`` may only read it.

Two shapes matter here:

* **The key set is fetched lazily.** Importing this module opens no connection,
  and neither does building the client - the first validated token is what
  fetches Zitadel's keys. ``PyJWKClient`` then caches them and refetches once on
  a ``kid`` it does not know, which is what makes a key rotation invisible to
  the operator instead of an outage.
* **Nothing is trusted from the token but its claims.** The algorithm list is
  ours, not the token's, and ``exp`` and ``sub`` are required rather than
  optional: a token that never expires, or that names no user, cannot be
  attributed to anybody.
* **The login comes from userinfo, not from the token.** Zitadel's claims
  matrix asserts ``preferred_username``, ``name`` and ``email`` in the ID token
  and at the userinfo endpoint, and never in an access token - so reading them
  off the bearer token would record a numeric subject for everybody. The name is
  fetched once per user and cached; the subject is the fallback when Zitadel
  cannot be reached, and it says so in the log.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
import requests
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientError

from tools.config import AuthSection

logger = logging.getLogger(__name__)

#: Where Zitadel puts the roles granted on the project a token was issued for.
#: The value is a mapping of role key to the organizations granting it; only the
#: keys matter to the panel.
PROJECT_ROLES_CLAIM = "urn:zitadel:iam:org:project:roles"

#: Zitadel signs with RS256. Naming it here is what stops a token from choosing
#: its own algorithm - `alg: none` is an attack, not a configuration.
_ALGORITHMS = ["RS256"]

#: Claims to read the operator's name from, best first. Checked on the token as
#: well as on the userinfo response: a Zitadel action can put one of them in the
#: access token, and then no lookup is needed at all.
_NAME_CLAIMS = ("preferred_username", "name", "email")

#: How long one resolved login is reused. Usernames change rarely, and the worst
#: a stale one costs is an out-of-date name against a job that already ran.
_NAME_TTL_SECONDS = 900

#: How long a failed lookup is remembered. Short, because it is a real outage
#: rather than a fact - but not zero, or an unreachable Zitadel would add a
#: timeout to every request the panel serves.
_NAME_FAILURE_TTL_SECONDS = 60

#: Long enough for a healthy round trip, short enough that an unresponsive
#: userinfo endpoint does not hold a panel request open.
_USERINFO_TIMEOUT_SECONDS = 3

_bearer = HTTPBearer(
    auto_error=False,
    description="Zitadel OIDC access token.",
)


class PanelRole(enum.StrEnum):
    """What a caller may do with the panel.

    ``worker`` is the superset: it may read everything a ``viewer`` can and
    additionally launch scans, cancel them, activate a snapshot and exclude or
    include a service. The values are the role keys as granted in Zitadel.
    """

    worker = "worker"
    viewer = "viewer"


@dataclass(frozen=True)
class Identity:
    """The authenticated caller behind one request.

    ``name`` is what ends up in ``job.initiated_by`` and in the exclusion
    record, so it is the login an operator would recognize, never the opaque
    subject - which is kept alongside it because it is the only claim that is
    guaranteed stable when someone changes their username.
    """

    subject: str
    name: str
    roles: frozenset[PanelRole]


def current_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Identity:
    """Validate the request's bearer token and return who sent it.

    A token that carries neither panel role is rejected as unauthenticated
    rather than forbidden: it belongs to somebody the panel has no relationship
    with at all, and answering ``403`` would confirm which of our endpoints
    exist to a caller who is not a principal here.
    """
    auth = _auth_settings(request)
    if credentials is None:
        raise _unauthenticated("no bearer token")

    claims = _claims(credentials.credentials, auth, _jwks_client(request, auth))
    roles = _panel_roles(claims)
    if not roles:
        raise _unauthenticated("token carries no panel role")
    return Identity(
        subject=str(claims["sub"]),
        name=_resolve_name(request, claims=claims, token=credentials.credentials),
        roles=frozenset(roles),
    )


def require_viewer(
    identity: Annotated[Identity, Depends(current_identity)],
) -> Identity:
    """Any authenticated caller. Reading the panel asks for nothing more."""
    return identity


def require_worker(
    identity: Annotated[Identity, Depends(current_identity)],
) -> Identity:
    """A caller who may change panel state.

    Separate from ``current_identity`` on purpose: the token was already valid,
    so this is a ``403`` about what the caller may do, not a ``401`` about who
    they are.
    """
    if PanelRole.worker not in identity.roles:
        logger.info(
            "%s tried a worker action with roles %s",
            identity.name,
            sorted(identity.roles),
        )
        raise HTTPException(
            status_code=403,
            detail="This action requires the worker role",
        )
    return identity


def _auth_settings(request: Request) -> AuthSection:
    """The issuer and audience to validate against, or a loud failure.

    An unconfigured panel refuses every request with a ``500`` rather than a
    ``401``: nobody could have sent a token that would work, so reporting it as
    the caller's problem would send an operator looking in the wrong place.
    """
    auth: AuthSection = request.app.state.settings.auth
    if not auth.issuer or not auth.audience:
        logger.error(
            "auth is not configured (AUTH__ISSUER / AUTH__AUDIENCE): "
            "refusing every authenticated request"
        )
        raise HTTPException(
            status_code=500,
            detail="Authentication is not configured on this panel",
        )
    return auth


def _jwks_client(request: Request, auth: AuthSection) -> PyJWKClient:
    """The app's JWKS client, built on first use and kept for the process.

    Constructing it fetches nothing, so this stays safe to reach during startup
    or in a test with no network; the cache lives on the app rather than in a
    module global so that a second app - which is what every test builds - does
    not inherit the first one's keys.
    """
    client = getattr(request.app.state, "jwks_client", None)
    if client is None:
        client = PyJWKClient(auth.jwks_url)
        request.app.state.jwks_client = client
    return client


def _claims(token: str, auth: AuthSection, jwks: PyJWKClient) -> dict[str, Any]:
    """Verify one token's signature, issuer, audience and expiry."""
    try:
        signing_key = jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience=auth.audience,
            issuer=auth.issuer,
            options={"require": ["exp", "sub"]},
        )
    except (jwt.PyJWTError, PyJWKClientError) as error:
        # The reason travels back to the caller: this is an internal panel, and
        # "expired" versus "wrong audience" is the difference between logging in
        # again and filing a ticket.
        logger.info("rejected a bearer token: %s", error)
        raise _unauthenticated(str(error)) from error


def _panel_roles(claims: dict[str, Any]) -> set[PanelRole]:
    """The panel roles this token grants.

    A role the panel does not define is ignored rather than refused: one Zitadel
    project can grant roles for several applications, and a caller holding
    another one's role is simply not a panel user.
    """
    granted = claims.get(PROJECT_ROLES_CLAIM)
    if not isinstance(granted, dict):
        return set()
    return {role for role in PanelRole if role.value in granted}


def _resolve_name(request: Request, *, claims: dict[str, Any], token: str) -> str:
    """The login to record for this caller.

    Checked on the token first, so a deployment that adds the claim through a
    Zitadel action pays for no lookup. Otherwise it is fetched from userinfo
    once per user and cached: a stock Zitadel access token carries no profile
    claim at all, and recording the numeric subject would make every job and
    exclusion unattributable to a person.

    This is the one network call in a request path, and it runs before any
    session is open: authentication is a router-level dependency, so it resolves
    ahead of the route's own ``get_db``. Keep it that way - a transaction held
    across this call is the shape this codebase avoids everywhere else.
    """
    subject = str(claims["sub"])
    from_token = _name_in(claims)
    if from_token is not None:
        return from_token

    cache = _name_cache(request)
    cached = cache.get(subject)
    if cached is not None and cached[1] > time.monotonic():
        return cached[0]

    auth: AuthSection = request.app.state.settings.auth
    try:
        info = _fetch_userinfo(auth.userinfo_url, token)
    except (requests.RequestException, ValueError) as error:
        # Not fatal: the request proceeds under the subject rather than failing
        # over a display name, and the log says the attribution degraded.
        logger.warning(
            "could not resolve a login for %s from %s (%s); "
            "recording the subject instead",
            subject,
            auth.userinfo_url,
            error,
        )
        cache[subject] = (subject, time.monotonic() + _NAME_FAILURE_TTL_SECONDS)
        return subject

    name = _name_in(info) or subject
    cache[subject] = (name, time.monotonic() + _NAME_TTL_SECONDS)
    return name


def _name_in(claims: dict[str, Any]) -> str | None:
    """The first name-like claim present, or None."""
    for claim in _NAME_CLAIMS:
        value = claims.get(claim)
        if value:
            return str(value)
    return None


def _name_cache(request: Request) -> dict[str, tuple[str, float]]:
    """Resolved logins by subject, kept on the app like the JWKS client."""
    cache = getattr(request.app.state, "name_cache", None)
    if cache is None:
        cache = {}
        request.app.state.name_cache = cache
    return cache


def _fetch_userinfo(url: str, token: str) -> dict[str, Any]:
    """Ask Zitadel who this token belongs to."""
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=_USERINFO_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _unauthenticated(reason: str) -> HTTPException:
    """A ``401`` that tells the client how to authenticate.

    The ``WWW-Authenticate`` header is what makes this a challenge rather than a
    flat refusal; the error handler passes it through to the response.
    """
    return HTTPException(
        status_code=401,
        detail=f"Not authenticated: {reason}",
        headers={"WWW-Authenticate": "Bearer"},
    )
