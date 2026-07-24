# New Python SDK Architecture for OpenTelekomCloud

**Status:** Proposal for review

---

## 1. Problems with Current python-otcextensions

The current Python SDK is built on top of openstacksdk and inherits its architectural decisions, causing systemic issues:

- **Heavy dependencies.** openstacksdk, keystoneauth1, os-service-types and the entire OpenStack ecosystem pull in dozens of transitive dependencies. Updating or debugging any of them affects the entire SDK.
- **Service coupling.** All services live in one package, share common code, and changes to one service can break others. It is impossible to install or update support for a single service independently.
- **Auth model incompatibility.** AK/SK authentication (AWS Signature V4) does not fit well into keystoneauth — SigV4 requires signing an already-formed HTTP request, while keystoneauth provides headers before request formation. Each new service with AK/SK requires individual workarounds.
- **Implicit contracts.** Request and response models are spread across proxy classes and resources with no clear boundary between input parameters and API responses.

---

## 2. Go SDK Architecture Analysis (gophertelekomcloud)

### 2.1. Overall Structure

The Go SDK has a minimalistic structure with **3 dependencies** (testify, golang.org/x/crypto, yaml.v2) and a clean layered organization:

```
gophertelekomcloud/
├── golangsdk (root package)
│   ├── auth_options.go          # AuthOptions — token/password auth
│   ├── auth_aksk_options.go     # AKSKAuthOptions — AK/SK auth
│   ├── auth_option_provider.go  # AuthOptionsProvider — unified interface
│   ├── provider_client.go       # ProviderClient — HTTP client with auth
│   ├── service_client.go        # ServiceClient — base service client
│   ├── endpoint_search.go       # EndpointOpts — endpoint discovery
│   ├── results.go               # Result — base response type
│   ├── params.go                # Parameter serialization utilities
│   └── signer_helper.go         # AK/SK signing (AWS SigV4)
│
├── internal/
│   ├── build/                   # Request body, query strings, headers
│   └── extract/                 # JSON response deserialization
│
├── openstack/
│   ├── client.go                # Factories: NewDNSV2(), NewComputeV2(), etc.
│   ├── common/                  # Shared utilities (tags, metadata, pointerto)
│   │
│   ├── dns/v2/                  # ← Typical service
│   │   ├── zones/
│   │   │   ├── requests.go      # CRUD functions + param types (CreateOpts, ListOpts)
│   │   │   ├── results.go       # Response models (Zone, CreateResult, GetResult)
│   │   │   └── urls.go          # URL constructors
│   │   ├── recordsets/
│   │   └── ...
│   │
│   ├── vpc/v1/                  # Each service is isolated
│   ├── cce/v3/
│   ├── elb/v3/
│   └── ... (59+ services)
│
└── pagination/                  # Pagination (linked, marker, offset, single)
```

### 2.2. Key Architectural Patterns

#### Pattern 1: Unified Auth Interface

A minimal `AuthOptionsProvider` interface with a single method `GetIdentityEndpoint()`. Two auth types — `AuthOptions` (token/password) and `AKSKAuthOptions` (AK/SK) — both implement this interface. Dispatch in `Authenticate()` determines the auth type via type assertion and calls the appropriate strategy:

```
AuthOptionsProvider (interface)
   ├── AuthOptions         → v3auth() or v3authWithAgency()
   └── AKSKAuthOptions     → v3AKSKAuth() or authWithAgencyByAKSK()
```

AK/SK signing is applied transparently at the `ProviderClient.Request()` level — if `AKSKAuthOptions.AccessKey` is set, the request is signed via `Sign()` before sending.

#### Pattern 2: Two-Level Client System

- **ProviderClient** — a single HTTP client that holds auth state (token, project ID, domain ID), reauth logic, retry/backoff. All requests go through its `Request()`.
- **ServiceClient** — a lightweight wrapper that adds endpoint and convenience methods (`Get`, `Post`, `Put`, `Patch`, `Delete`). Created via factories in `client.go` (e.g. `NewDNSV2(provider, endpointOpts)`).

#### Pattern 3: Each Resource Is an Isolated Package

Each resource (zones, recordsets, publicips, ...) is a separate package with three files:

| File | Contents |
|------|----------|
| `requests.go` | CRUD functions (free functions, not methods). Input parameter types (`CreateOpts`, `ListOpts`) with builder interfaces (`CreateOptsBuilder`). Validation via struct tags. |
| `results.go` | Response models (`Zone`, `CreateResult`, `GetResult`). Inherit from `golangsdk.Result` for lazy extraction via `Extract()`. |
| `urls.go` | Pure URL construction functions using `ServiceClient.ServiceURL()`. |

Functions take `*ServiceClient` as their first argument — no magic proxies or resource classes.

#### Pattern 4: Minimal External Dependencies

The Go SDK deliberately avoids OpenStack-specific libraries. Everything, including AK/SK signing, is implemented inside the repository. This provides full control and eliminates breaking changes from upstream.

---

## 3. Target Architecture for New Python SDK

### 3.1. Package Structure

```
otc-sdk-python/
├── pyproject.toml               # Minimal deps: httpx, pydantic
│
├── src/otc_sdk/
│   ├── __init__.py
│   │
│   ├── core/                    # ← Analogue of root golangsdk package
│   │   ├── auth.py              # AuthOptions, AKSKAuthOptions, AuthProvider (Protocol)
│   │   ├── signer.py            # AK/SK signing (SigV4) — own implementation
│   │   ├── provider.py          # ProviderClient — HTTP client + auth
│   │   ├── service_client.py    # ServiceClient — base client for services
│   │   ├── endpoint.py          # EndpointOpts, endpoint discovery
│   │   ├── result.py            # Base result types
│   │   ├── exceptions.py        # Exception hierarchy
│   │   └── pagination.py        # Pagination strategies (linked, marker, offset)
│   │
│   ├── services/                # ← Analogue of openstack/
│   │   ├── __init__.py
│   │   │
│   │   ├── dns/                 # Each service is a subpackage
│   │   │   ├── __init__.py
│   │   │   ├── v2/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── client.py    # DnsV2Client with factory methods
│   │   │   │   ├── zones/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── requests.py   # create(), list_zones(), get(), ...
│   │   │   │   │   ├── models.py     # CreateOpts, Zone, ListOpts (pydantic)
│   │   │   │   │   └── urls.py       # base_url(), zone_url()
│   │   │   │   ├── recordsets/
│   │   │   │   └── ...
│   │   │   └── ...
│   │   │
│   │   ├── vpc/
│   │   ├── cce/
│   │   ├── elb/
│   │   └── ...
│   │
│   └── common/                  # Shared utilities
│       ├── tags.py
│       └── metadata.py
│
├── tests/
│   ├── unit/
│   │   ├── core/
│   │   └── services/
│   └── acceptance/
│       └── services/
│
└── docs/
```

### 3.2. Core Abstractions

#### AuthProvider (Protocol)

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class AuthProvider(Protocol):
    """Unified interface for all auth strategies."""

    @property
    def identity_endpoint(self) -> str: ...
```

#### Auth Strategies

```python
from pydantic import BaseModel


class AuthOptions(BaseModel):
    """Token/Password authentication."""

    identity_endpoint: str
    username: str | None = None
    user_id: str | None = None
    password: str | None = None
    domain_id: str | None = None
    domain_name: str | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    token_id: str | None = None
    allow_reauth: bool = False
    agency_name: str | None = None
    agency_domain_name: str | None = None
    delegated_project: str | None = None


class AKSKAuthOptions(BaseModel):
    """AK/SK authentication (AWS Signature V4)."""

    identity_endpoint: str
    access_key: str
    secret_key: str
    project_id: str | None = None
    project_name: str | None = None
    region: str | None = None
    domain: str | None = None
    domain_id: str | None = None
    security_token: str | None = None
```

#### ProviderClient

```python
import httpx


class ProviderClient:
    """Central HTTP client. Manages auth, retry, reauth."""

    def __init__(self, auth: AuthProvider):
        self.identity_base: str = ""
        self.identity_endpoint: str = auth.identity_endpoint
        self.token_id: str | None = None
        self.project_id: str | None = None
        self.domain_id: str | None = None
        self.aksk_options: AKSKAuthOptions | None = None
        self._http: httpx.Client = httpx.Client()
        self._reauth_func: Callable | None = None

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send request with auth, retry, reauth."""
        # 1. Add auth headers (X-Auth-Token or AK/SK signature)
        # 2. Send request
        # 3. Handle 401 → reauth → retry
        # 4. Handle 429 → backoff → retry
        # 5. Handle errors → typed exceptions
        ...
```

#### ServiceClient

```python
class ServiceClient:
    """Base client for a specific service."""

    def __init__(
        self, provider: ProviderClient, endpoint: str, resource_base: str | None = None
    ):
        self.provider = provider
        self.endpoint = endpoint
        self.resource_base = resource_base or endpoint

    def service_url(self, *parts: str) -> str:
        return self.resource_base + "/".join(parts)

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.provider.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.provider.request("POST", url, **kwargs)

    # put, patch, delete similarly
```

### 3.3. Service Implementation Example (DNS Zones)

#### models.py

```python
from pydantic import BaseModel


class CreateZoneOpts(BaseModel):
    name: str
    email: str | None = None
    description: str | None = None
    ttl: int | None = None
    zone_type: str | None = None


class Zone(BaseModel):
    id: str
    name: str
    email: str | None = None
    description: str | None = None
    ttl: int | None = None
    status: str | None = None
    zone_type: str | None = None
    record_num: int | None = None
    pool_id: str | None = None
    project_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ListZonesOpts(BaseModel):
    limit: int | None = None
    marker: str | None = None
    name: str | None = None
    status: str | None = None
    type: str | None = None
```

#### urls.py

```python
from otc_sdk.core.service_client import ServiceClient

ROOT = "zones"


def base_url(client: ServiceClient) -> str:
    return client.service_url(ROOT)


def zone_url(client: ServiceClient, zone_id: str) -> str:
    return client.service_url(ROOT, zone_id)
```

#### requests.py

```python
from typing import Iterator
from otc_sdk.core.service_client import ServiceClient
from .models import CreateZoneOpts, Zone, ListZonesOpts
from . import urls


def create(client: ServiceClient, opts: CreateZoneOpts) -> Zone:
    resp = client.post(
        urls.base_url(client),
        json=opts.model_dump(exclude_none=True),
    )
    return Zone.model_validate(resp.json())


def get(client: ServiceClient, zone_id: str) -> Zone:
    resp = client.get(urls.zone_url(client, zone_id))
    return Zone.model_validate(resp.json())


def list_zones(
    client: ServiceClient, opts: ListZonesOpts | None = None
) -> Iterator[Zone]:
    """Iterator that automatically walks through all pages."""
    url = urls.base_url(client)
    params = opts.model_dump(exclude_none=True) if opts else {}
    while url:
        resp = client.get(url, params=params)
        data = resp.json()
        for z in data["zones"]:
            yield Zone.model_validate(z)
        url = data.get("links", {}).get("next")
        params = {}  # params already embedded in next URL


def delete(client: ServiceClient, zone_id: str) -> None:
    client.delete(urls.zone_url(client, zone_id))
```

> **Proposal: Generator-based pagination.** In Go, pagination uses `pagination.Pager` with callbacks. In Python, the natural approach is an iterator with `yield` that automatically fetches subsequent pages. The user should never have to think about markers:
>
> ```python
> for zone in zones.list_zones(client):
>     print(zone.name)
> ```

### 3.4. Client Factory

```python
# otc_sdk/client.py — main entry point


class OTCClient:
    """Main entry point. Creates ProviderClient and service factories."""

    def __init__(self, auth: AuthProvider):
        self.provider = ProviderClient(auth)
        authenticate(self.provider, auth)

    def dns_v2(self, region: str | None = None) -> ServiceClient:
        endpoint = self.provider.find_endpoint("dns", region=region)
        return ServiceClient(self.provider, endpoint, resource_base=endpoint + "v2/")

    def vpc_v1(self, region: str | None = None) -> ServiceClient: ...


def authenticate(provider: ProviderClient, auth: AuthProvider) -> None:
    """Determine auth type and authenticate."""
    if isinstance(auth, AKSKAuthOptions):
        provider.aksk_options = auth
        _aksk_auth(provider, auth)
    elif isinstance(auth, AuthOptions):
        _token_auth(provider, auth)
    else:
        raise TypeError(f"Unknown auth type: {type(auth)}")
```

> **Proposal: Lazy imports for services.** Eagerly importing all 50+ services in `__init__.py` would slow down `import otc_sdk`. Instead, use lazy properties that import a service only on first access:
>
> ```python
> class OTCClient:
>     @property
>     def dns(self):
>         from otc_sdk.services.dns.v2 import client as dns_client
>         return dns_client.DnsV2Client(self.provider)
> ```
>
> This ensures fast application startup — only services that are actually used get imported. No entry point or plugin magic needed.

### 3.5. Usage Example

```python
from otc_sdk import OTCClient
from otc_sdk.core.auth import AuthOptions, AKSKAuthOptions
from otc_sdk.services.dns.v2 import zones

# Token authentication
client = OTCClient(
    AuthOptions(
        identity_endpoint="https://iam.eu-de.otc.t-systems.com/v3",
        username="user",
        password="pass",
        domain_name="domain",
        tenant_name="eu-de",
    )
)

# Or AK/SK
client = OTCClient(
    AKSKAuthOptions(
        identity_endpoint="https://iam.eu-de.otc.t-systems.com/v3",
        access_key="AK...",
        secret_key="SK...",
        project_id="...",
        region="eu-de",
    )
)

# API works identically regardless of auth type
dns = client.dns_v2()
zone = zones.create(
    dns, zones.CreateZoneOpts(name="example.com.", email="admin@example.com")
)

for z in zones.list_zones(dns):
    print(z.name)
```

---

## 4. Go → Python Mapping

| Go SDK | Python SDK | Notes |
|--------|-----------|-------|
| `AuthOptionsProvider` (interface) | `AuthProvider` (Protocol) | runtime_checkable |
| `AuthOptions` struct | `AuthOptions(BaseModel)` | pydantic validation |
| `AKSKAuthOptions` struct | `AKSKAuthOptions(BaseModel)` | pydantic validation |
| `ProviderClient` | `ProviderClient` | httpx instead of net/http |
| `ServiceClient` | `ServiceClient` | Thin wrapper |
| `Sign()` | `sign_request()` | Own SigV4 implementation |
| `openstack/client.go` (factories) | `OTCClient` | Factory methods |
| `openstack/dns/v2/zones/` package | `services/dns/v2/zones/` package | 1:1 mapping |
| `requests.go` (free functions) | `requests.py` (free functions) | Not class methods |
| `results.go` (struct + Extract) | `models.py` (pydantic BaseModel) | model_validate instead of Extract |
| `urls.go` | `urls.py` | Pure functions |
| `CreateOptsBuilder` (interface) | pydantic `BaseModel` | Validation via pydantic |
| struct tags (`json:`, `q:`, `required:`) | pydantic Field + model_dump | exclude_none for optionals |
| `golangsdk.Result.ExtractInto()` | `pydantic.BaseModel.model_validate()` | Automatic deserialization |
| `pagination.Pager` | Iterator/generator | Pythonic approach |
| `go.mod` (3 dependencies) | `pyproject.toml` (httpx + pydantic) | Minimal dependencies |

---

## 5. Dependencies

| Dependency | Purpose | Notes |
|------------|---------|-------|
| `httpx` | HTTP client | Sync + async out of the box. MVP is sync-only, architecture is async-ready |
| `pydantic` | Model validation | Replaces Go struct tags |

Everything else (SigV4 signing, retry, pagination) is **implemented internally**. No openstacksdk, keystoneauth, or os-service-types.

---

## 6. Principles

1. **Zero service coupling.** Each service is an isolated subpackage. Depends only on `core/`.
2. **Explicit contracts.** Typed pydantic models for every request and response. No `dict` or `**kwargs` in the public API.
3. **Own auth implementation.** Unified `AuthProvider` Protocol. Token and AK/SK as interchangeable strategies. SigV4 signing implemented inside the SDK.
4. **Free functions for operations.** `zones.create(client, opts)` instead of `client.zones.create(opts)`. Follows the Go pattern — easier to test and generate.
5. **Minimal dependencies.** Only httpx + pydantic. Full control over the codebase.
6. **Type hinting & IDE support.** 100% type hint coverage thanks to pydantic and explicit function signatures.

> **Proposal: Functional style justification.** The functional approach may look unusual to Python developers accustomed to boto3 or azure-sdk (`client.zones.create(opts)`). However, free functions are stateless — `create`, `list` are pure and take a client as a dependency. This simplifies mocking in tests, eliminates circular imports, and dramatically simplifies code generation. We keep the functional approach.

> **Proposal: Type hinting as a selling point.** In the current SDK (dynamic proxies from openstacksdk), autocomplete in VS Code and PyCharm barely works. In the new SDK — pydantic models with typed fields + explicit function signatures mean IDEs will suggest `CreateZoneOpts` fields and `Zone` response field types. This is a significant developer experience improvement.

---

## 7. Code Generation Benefits (gen-sdk-tooling)

This architecture is well suited for automatic SDK generation from RST documentation:

- **Uniform structure** for every service → Jinja2 templates for `models.py`, `requests.py`, `urls.py`.
- **Pydantic models** are generated directly from request/response specs found in RST.
- **Free functions** instead of classes → simpler templates, less inheritance.
- **No OpenStack dependency** → no need to maintain compatibility with external code.

---

## 8. Implementation Plan

### Phase 1: Core (2–3 weeks)

- `core/auth.py` — AuthOptions, AKSKAuthOptions, AuthProvider
- `core/signer.py` — AK/SK signing (ported from Go)
- `core/provider.py` — ProviderClient with auth, retry, reauth
- `core/service_client.py` — ServiceClient
- `core/exceptions.py` — exception hierarchy
- `core/pagination.py` — pagination strategies

### Phase 2: Pilot Service (1–2 weeks)

- Implement DNS v2 manually as a reference
- Write acceptance tests against real OTC
- Debug auth flow for both token and AK/SK

### Phase 3: Generation (parallel with gen-sdk-tooling)

- Jinja2 templates for models.py, requests.py, urls.py
- Generate SDK for 2–3 services, compare with reference
- Iterate on generation quality

### Phase 4: Scaling

- Generate remaining 50+ services
- CI/CD pipeline for automatic regeneration

---

## 9. Decisions on Open Questions

> **Proposal:** Close the open questions with the following decisions so this section reads as an action plan rather than uncertainty.

1. **Async support.**
   *Decision:* MVP (Phases 1–2) implements sync API only (`httpx.Client`). The architecture is async-ready: httpx has an identical API for sync and async, and free functions allow adding `async def create(...)` + `httpx.AsyncClient` later with minimal generator changes (template swap).

2. **Package naming.**
   *Decision:* `otc-sdk` (PyPI) / `import otc_sdk`. Short and clear. `otcextensions` is a bad legacy name.

3. **Service discovery.**
   *Decision:* Lazy properties in `OTCClient` (see proposal in section 3.4). Only services that are actually used get imported. No entry points or plugin magic.

4. **Backward compatibility.**
   *Decision:* Full replacement (major version). Maintaining compatibility with the openstacksdk architecture is impossible and counterproductive — it is the root of the problems. The old and new SDKs can be installed side by side (`pip install otc-sdk` alongside `pip install python-otcextensions`).

5. **Paginators.**
   *Decision:* Python iterators with `yield` (see proposal in section 3.3). `for zone in zones.list_zones(client)` — automatic traversal of all pages.