"""Bearer-token authentication and the two panel roles.

Zitadel is never contacted: the tests mint tokens with a local RSA key and hand
the app the matching public key through the same seam production uses for the
cached JWKS client. So the signature, the issuer, the audience and the expiry
are all really verified here - only the key transport is local.

Needs PostgreSQL like the other API suites (see tests/test_panel_db.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("alembic")
pytest.importorskip("httpx")
pytest.importorskip("jwt")

import jwt  # noqa: E402
from alembic import command  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from tests.test_panel_db import (  # noqa: E402,F401  (reused DB fixtures)
    _alembic_config,
    admin_url,
    scratch_database,
)
from tools.config import Settings  # noqa: E402
from tools.panel.api import deps  # noqa: E402
from tools.panel.api.app import create_app  # noqa: E402
from tools.panel.api.auth import PROJECT_ROLES_CLAIM, _jwks_client  # noqa: E402
from tools.panel.api.routes import scans as scans_module  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
)

ISSUER = "https://panel.zitadel.test"
AUDIENCE = "123456789@gen_sdk_panel"
REPO = "opentelekomcloud-docs/ecs"
KEY_ID = "local-test-key"

#: Every endpoint a token has to reach, and the role it takes. The suite is
#: driven from this table so an endpoint added without an entry shows up as a
#: gap here rather than as an unguarded route in production.
READS = [
    "/api/scan/summary",
    "/api/scan/attention",
    "/api/scan/excluded",
    "/api/scan/ineligible",
    "/api/scan/services",
    f"/api/scan/services/{REPO}",
    f"/api/scan/services/{REPO}/snapshots",
    f"/api/scan/services/{REPO}/documents",
    f"/api/scan/services/{REPO}/documents/1",
    f"/api/scan/services/{REPO}/export",
    "/api/jobs/1",
]

MUTATIONS = [
    (f"/api/scan/services/{REPO}/rescan", {"initiated_by": "body-says-this"}),
    (f"/api/scan/services/{REPO}/snapshots/1/activate", {"initiated_by": "body"}),
    (f"/api/scan/services/{REPO}/exclude", {"reason": "r", "initiated_by": "body"}),
    (f"/api/scan/services/{REPO}/include", None),
    ("/api/jobs/1/cancel", None),
]


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    """One key pair for the module: generating RSA keys is slow."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def engine(scratch_database):  # noqa: F811  (pytest fixture injection)
    url = scratch_database("panel_test_auth")
    command.upgrade(_alembic_config(url), "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def client(session_factory, signing_key, monkeypatch):
    """The panel with authentication live, trusting only the local key."""
    app = create_app()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    app.state.settings = Settings(auth={"issuer": ISSUER, "audience": AUDIENCE})
    # The seam production uses to cache Zitadel's keys, holding the local public
    # key instead. Everything downstream of it is the real verification path.
    app.state.jwks_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(
            key=signing_key.public_key()
        )
    )
    # `scans.py` binds the runner at import, so this is the name that is
    # actually called. Nothing in this suite is about scanning: a launched job
    # stays queued, which is also what lets the registry show who queued it.
    monkeypatch.setattr(scans_module, "run_scan_job", lambda _job_id: None)
    return TestClient(app)


def _token(signing_key, *, roles=("worker",), **overrides) -> str:
    """Mint a token Zitadel could have issued."""
    now = datetime.now(tz=UTC)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-1234",
        "preferred_username": "ada@otc.test",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        PROJECT_ROLES_CLAIM: {role: {"orgid": "otc.test"} for role in roles},
    }
    claims.update(overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": KEY_ID})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(session_factory, repo: str = REPO) -> int:
    with session_factory() as session:
        service = Service(repo=repo, name=repo.split("/")[-1], branch="main")
        session.add(service)
        session.commit()
        return service.id


# ---------------------------------------------------------------------------
# Who gets in
# ---------------------------------------------------------------------------


def test_every_api_operation_requires_a_token(client):
    """Closed by default, checked against the published contract rather than
    FastAPI's route table: a route added to either scan router without
    authentication has no security requirement here, and this fails."""
    schema = client.get("/openapi.json").json()
    api = [
        (f"{method.upper()} {path}", operation)
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if path.startswith("/api")
    ]

    unguarded = [
        name
        for name, operation in api
        if operation.get("security") != [{"HTTPBearer": []}]
    ]

    assert unguarded == []
    assert api  # the filter matched something; an empty list would prove nothing


def test_health_needs_no_token(client):
    """The container healthcheck and the load balancer poll this and hold no
    token; requiring one would make an unauthenticated panel look down."""
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", READS)
def test_a_read_without_a_token_is_401(client, path):
    resp = client.get(path)

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"
    # The challenge is what tells a client how to authenticate at all.
    assert resp.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("path,body", MUTATIONS)
def test_a_mutation_without_a_token_is_401(client, path, body):
    assert client.post(path, json=body).status_code == 401


def test_an_expired_token_is_401(client, signing_key):
    past = datetime.now(tz=UTC) - timedelta(minutes=1)
    token = _token(signing_key, exp=past, iat=past - timedelta(minutes=5))

    resp = client.get("/api/scan/summary", headers=_auth(token))

    assert resp.status_code == 401
    assert "expired" in resp.json()["error"]["message"].lower()


def test_a_token_for_another_audience_is_401(client, signing_key):
    """A token minted for a different application of the same Zitadel project
    verifies against the same keys, so the audience is the only thing standing
    between that application's users and this one's."""
    token = _token(signing_key, aud="some-other-application")

    resp = client.get("/api/scan/summary", headers=_auth(token))

    assert resp.status_code == 401
    assert "audience" in resp.json()["error"]["message"].lower()


def test_a_token_from_another_issuer_is_401(client, signing_key):
    token = _token(signing_key, iss="https://impostor.example")

    assert client.get("/api/scan/summary", headers=_auth(token)).status_code == 401


def test_a_token_signed_by_someone_else_is_401(client):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _token(other_key)

    assert client.get("/api/scan/summary", headers=_auth(token)).status_code == 401


def test_a_token_with_no_panel_role_is_401(client, signing_key):
    """Not a 403: a caller holding only another application's roles is not a
    principal of this panel at all, and 403 would confirm what exists here."""
    token = _token(signing_key, roles=("some-other-app-role",))

    resp = client.get("/api/scan/summary", headers=_auth(token))

    assert resp.status_code == 401


def test_a_token_without_an_expiry_is_401(client, signing_key):
    """`exp` is required, not optional: a token that never expires cannot be
    withdrawn, and Zitadel always sets one."""
    token = _token(signing_key)
    forever = jwt.decode(token, options={"verify_signature": False})
    forever.pop("exp")
    token = jwt.encode(forever, signing_key, algorithm="RS256")

    assert client.get("/api/scan/summary", headers=_auth(token)).status_code == 401


def test_an_unconfigured_panel_refuses_with_500_not_401(client, signing_key):
    """Nobody could hold a token that would work, so this is the operator's
    problem, not the caller's - reporting 401 would send them to their IdP."""
    client.app.state.settings = Settings(auth={"issuer": "", "audience": ""})

    resp = client.get("/api/scan/summary", headers=_auth(_token(signing_key)))

    assert resp.status_code == 500
    assert "not configured" in resp.json()["error"]["message"]


def test_the_jwks_client_is_built_from_the_issuer_and_kept(client):
    """The production path the other tests inject past. Building the client
    fetches nothing, which is what lets this module be imported - and this test
    run - without a network; the app keeps it so the keys are cached across
    requests rather than refetched per token."""
    app = client.app
    del app.state.jwks_client  # drop the local stand-in
    request = SimpleNamespace(app=app)

    first = _jwks_client(request, app.state.settings.auth)
    second = _jwks_client(request, app.state.settings.auth)

    assert first.uri == f"{ISSUER}/oauth/v2/keys"
    assert second is first


def test_a_roles_claim_that_is_not_a_mapping_grants_nothing(client, signing_key):
    """Zitadel writes a mapping; anything else is a token this panel cannot
    read roles from, and guessing at it would be inventing an authorization."""
    token = _token(signing_key, **{PROJECT_ROLES_CLAIM: "worker"})

    assert client.get("/api/scan/summary", headers=_auth(token)).status_code == 401


# ---------------------------------------------------------------------------
# What each role may do
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", READS)
def test_a_viewer_reads_everything(client, session_factory, signing_key, path):
    _register(session_factory)
    token = _token(signing_key, roles=("viewer",))

    resp = client.get(path, headers=_auth(token))

    # 404 where the fixture holds no such row; never 401 or 403, which are the
    # answers this test is about.
    assert resp.status_code in (200, 404)


@pytest.mark.parametrize("path,body", MUTATIONS)
def test_a_viewer_is_forbidden_from_every_mutation(
    client, session_factory, signing_key, path, body
):
    _register(session_factory)
    token = _token(signing_key, roles=("viewer",))

    resp = client.post(path, json=body, headers=_auth(token))

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
    assert "worker" in resp.json()["error"]["message"]


@pytest.mark.parametrize("path", READS)
def test_a_worker_reads_everything_too(client, session_factory, signing_key, path):
    _register(session_factory)

    resp = client.get(path, headers=_auth(_token(signing_key)))

    assert resp.status_code in (200, 404)


@pytest.mark.parametrize("path,body", MUTATIONS)
def test_a_worker_is_never_refused_a_mutation(
    client, session_factory, signing_key, path, body
):
    """Each of these fails on its own terms - no such job, no such snapshot,
    not excluded - which is the point: the role check is behind it."""
    _register(session_factory)

    resp = client.post(path, json=body, headers=_auth(_token(signing_key)))

    assert resp.status_code not in (401, 403)


def test_a_worker_holding_the_viewer_role_too_is_still_a_worker(
    client, session_factory, signing_key
):
    _register(session_factory)
    token = _token(signing_key, roles=("viewer", "worker"))

    resp = client.post(
        f"/api/scan/services/{REPO}/rescan",
        json={"initiated_by": "ignored"},
        headers=_auth(token),
    )

    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def test_the_job_records_the_token_identity_not_the_body(
    client, session_factory, signing_key
):
    """`initiated_by` is an attribution, so it can only come from the token.
    The body still carries the field and is still ignored."""
    _register(session_factory)

    resp = client.post(
        f"/api/scan/services/{REPO}/rescan",
        json={"initiated_by": "somebody-else"},
        headers=_auth(_token(signing_key)),
    )

    assert resp.status_code == 202
    with session_factory() as session:
        job = session.scalars(select(RepositoryScanJob)).one()
        assert job.initiated_by == "ada@otc.test"


def test_the_exclusion_records_the_token_identity_not_the_body(
    client, session_factory, signing_key
):
    _register(session_factory)

    client.post(
        f"/api/scan/services/{REPO}/exclude",
        json={"reason": "retired", "initiated_by": "somebody-else"},
        headers=_auth(_token(signing_key)),
    )

    (row,) = client.get("/api/scan/excluded", headers=_auth(_token(signing_key))).json()
    assert row["excluded_by"] == "ada@otc.test"


def test_the_identity_falls_back_to_the_subject(client, session_factory, signing_key):
    """Zitadel always sends `sub`; the friendlier claims are configurable per
    application, so the attribution cannot depend on them being there."""
    _register(session_factory)
    token = _token(signing_key, preferred_username="", name="", email="")

    client.post(
        f"/api/scan/services/{REPO}/rescan",
        json={"initiated_by": "ignored"},
        headers=_auth(token),
    )

    with session_factory() as session:
        assert (
            session.scalars(select(RepositoryScanJob)).one().initiated_by == "user-1234"
        )


def test_the_scanning_service_reports_the_token_identity(
    client, session_factory, signing_key
):
    """What the registry shows while a scan runs is the same attribution, so an
    operator can see who started what."""
    _register(session_factory)
    client.post(
        f"/api/scan/services/{REPO}/rescan",
        json={"initiated_by": "ignored"},
        headers=_auth(_token(signing_key)),
    )

    (item,) = client.get(
        "/api/scan/services", headers=_auth(_token(signing_key))
    ).json()["items"]

    assert item["initiated_by"] == "ada@otc.test"


def test_a_queued_job_is_visible_to_a_viewer(client, session_factory, signing_key):
    """Reading who is scanning is a read: a viewer sees the attribution even
    though they could not have created it."""
    service_id = _register(session_factory)
    with session_factory() as session:
        session.add(
            RepositoryScanJob(
                service_id=service_id,
                kind=JobKind.scan,
                status=JobStatus.queued,
                initiated_by="ada@otc.test",
            )
        )
        session.commit()

    body = client.get(
        f"/api/scan/services/{REPO}",
        headers=_auth(_token(signing_key, roles=("viewer",))),
    ).json()

    assert body["initiated_by"] == "ada@otc.test"
