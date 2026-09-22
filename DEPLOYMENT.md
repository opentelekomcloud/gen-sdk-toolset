# Deploying the scan panel

What the panel is made of, what each part needs from its environment, and what
it reaches out to. This is the operator's document: the repository ships two
images and this file, and the deployment itself - cluster, ingress, TLS,
database, secrets - is whatever the platform does.

Authentication has its own document: [AUTHORIZATION.md](AUTHORIZATION.md).

## Images

Both are built and pushed by CI on a tag or a release
(`.github/workflows/docker-push-release.yaml`, after
`opentelekomcloud-infra/circle-partner-navigator-frontend`); a tag `v1.2.3`
produces the pair below with the same version. They go to SWR under
`t-cloud-public`; the host and the credentials are the organization secrets
`SWR_URL`, `SWR_USERNAME`, `SWR_PASSWORD`. Deploy them together - the
frontend's API types are generated from the backend's schema at that version.

| Image | Built from | Serves |
|---|---|---|
| `<SWR>/t-cloud-public/sdk-panel` | `Dockerfile.backend` | the API on port `8000`, and the scanner inside it |
| `<SWR>/t-cloud-public/sdk-panel-frontend` | `Dockerfile.frontend` | the UI as static files on port `8080`, as the nginx user (uid 101) |

### Building the images

The base images are Docker Hardened Images from the organization's
Artifactory (`${ARTIFACTORY_URL}/dhi.io/python:3.13-dev`,
`.../node:24-alpine-dev`, `.../nginx:1-alpine-dev`). Any build - CI, a laptop,
`docker compose up --build` - needs the host as the build argument
`ARTIFACTORY_URL` and a `docker login` to it. In CI both come from the
organization secrets `ARTIFACTORY_URL`, `ARTIFACTORY_AUTH_USERNAME`,
`ARTIFACTORY_AUTH_PASSWORD`; locally, `ARTIFACTORY_URL` goes into `.env` and
the login is done once by hand.

## Components

| Component | Image | Command | Replicas |
|---|---|---|---|
| backend | `sdk-panel` | the image default: `alembic upgrade head`, then `uvicorn` on `:8000` | **exactly 1** - see [Limits](#limits) |
| frontend | `sdk-panel-frontend` | the image default: nginx on `:8080` | any |
| discovery | `sdk-panel` | `uv run panel discover` | one at a time, on a schedule |
| PostgreSQL 16 | not shipped | - | provided by the platform |

**Routing.** One host. `/api/*` goes to the backend (`:8000`), everything else to the
frontend (`:8080`). The frontend image serves no `/api` itself (nginx answers `404`
there), and the backend serves no UI. Same origin for both is what the
`PANEL__FRONTEND_ORIGIN` setting below assumes.

**Health.** `GET /health` on the backend answers `200 {"status":"ok"}` and is
the only route that needs no token - use it for readiness and liveness. It
does not have to be reachable from outside.

**TLS** is required end to end: the Zitadel redirect URI is the panel's public
URL, and Zitadel refuses a plain `http://` one outside localhost.

**Discovery** is a scheduled run of the backend image with a different command.
One pass registers repositories that appeared in the GitHub organization,
refreshes each known repository's branch HEAD (what every "documentation
changed" mark on the panel is compared against), and exits. It never starts a
scan. Every four hours is plenty (`17 */4 * * *`); do not run two passes at
once. A pass interrupted by a rate limit keeps what it wrote and exits
non-zero; the next pass finishes the work, so no retry policy is needed - a
run that fails every time is a configuration problem, and its output says
which.

## Environment

| Variable | Component | Secret | Value |
|---|---|---|---|
| `DATABASE__URL` | backend, discovery | yes | `postgresql+psycopg://<user>:<password>@<host>:5432/<db>` |
| `AUTH__ISSUER` | backend | no | the Zitadel instance URL, e.g. `https://<instance>.zitadel.cloud` |
| `AUTH__AUDIENCE` | backend | no | client id of the panel's **API** application in Zitadel |
| `PANEL__FRONTEND_ORIGIN` | backend | no | the panel's public URL, e.g. `https://panel.example.com` |
| `GITHUB_TOKEN` | discovery; backend only if scans run here | yes | GitHub PAT, see [Access](#access) |
| `ZITADEL_ISSUER` | frontend | no | same instance URL as `AUTH__ISSUER` |
| `ZITADEL_CLIENT_ID` | frontend | no | client id of the panel's **SPA** application in Zitadel |
| `ZITADEL_SCOPE` | frontend | no | `openid profile email urn:zitadel:iam:org:project:id:<project id>:aud` |

Optional, backend and discovery - the image carries no `scan-config.toml`, so
these override the built-in defaults the same way the file would:

| Variable | Default | Meaning |
|---|---|---|
| `GITHUB__ORG` | `opentelekomcloud-docs` | organization discovery lists |
| `GITHUB__BRANCH` | `main` | branch discovery reads HEAD from and scans run at |
| `SCANNER__MAX_WORKERS` | `8` | concurrent file fetches per scan; more trips GitHub's secondary rate limit |
| `LOGGING__LEVEL` | `INFO` | standard Python level |

Logs go to stdout, one line per record. PostgreSQL is used as is: version 16,
no extensions, one database with one owner role.

Nothing is baked into either image. The backend reads its settings at start;
the frontend container writes `/config.js` from its three variables at start,
so changing a Zitadel value is a restart, not a rebuild.

Without `AUTH__ISSUER` and `AUTH__AUDIENCE` the backend starts, answers
`/health`, and answers `500` to everything under `/api` - it has nothing to
validate a token against and says so rather than letting anyone in. Without
`ZITADEL_ISSUER` and `ZITADEL_CLIENT_ID` the UI shows "sign-in is not
configured" instead of a sign-in button.

## Access

**Outbound, backend and discovery**

- `https://api.github.com` - discovery lists the organization's repositories
  and reads branch HEADs; a scan reads a repository's `api-ref/source/` files.
- `<AUTH__ISSUER>/oauth/v2/keys` and `<AUTH__ISSUER>/oidc/v1/userinfo` - token
  signing keys (fetched on the first request, cached) and the signed-in user's
  name.
- PostgreSQL.

**Outbound, frontend:** none. The browser talks to Zitadel directly.

**Inbound:** only through the ingress. The backend and the database are never
published.

**GitHub token.** A classic personal access token with the single scope
`public_repo` - the scanner only reads public repositories of
`opentelekomcloud-docs`. Use a service account, not a person's token: it is
the identity every scan and discovery run acts under. Discovery spends about
one request per repository per pass; a scan spends one per documentation file.
The limit is 5 000 requests per hour per token, and both share it.

**Who may reach the panel.** The API refuses every request without a valid
Zitadel token and the UI signs users in through Zitadel, so only accounts of
the Zitadel organization can use it. Whether the host is also restricted to
the corporate network is a platform decision; the panel does not require it.

## Scans: on the host or not

The scanner runs inside the backend process. Whether a `worker` can launch a
scan from the panel depends only on whether the backend has a `GITHUB_TOKEN`:

- **With it**, rescans work from the UI, and the token's quota is spent by
  whoever clicks. This is the intended mode.
- **Without it**, the panel is read-only with respect to new data: it serves
  what is in the database, and scans are run elsewhere and loaded in. This is
  how the previous staging host ran.

Discovery needs the token in either mode.

## Limits

Written down so that they are not surprises:

- **One backend replica.** Migrations run at container start, and a scan runs
  as a background task of the API process; a second replica would race both.
- **A scan does not survive a restart.** The job stays in the database, but
  the thread behind it is gone. The backend closes such jobs at its next start
  (they show as failed with a reason) and the scan has to be launched again.
  Plan restarts and rollouts around running scans.
- **One scan per service at a time**, enforced by the database.
- **Migrations apply at start** against whatever database the backend finds.
  Fine for a deployment that owns its database; back it up before an upgrade
  all the same.
- **No backups are shipped.** The database is the only state.

## First start

The database is created empty by the migrations at the backend's first start.
To populate it, run one discovery pass (registers every repository of the
organization), then launch scans from the panel as a `worker`. Start from an
empty database rather than a dump of an older panel: snapshots written before
the eight-section document layout cannot be read back by this version.

## Smoke check

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/health            # 200
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/api/scan/summary  # 401
```

Then, in a browser: a `viewer` account signs in and sees the panel without
any rescan, activate or exclude control; a `worker` account sees them; a deep
link such as `https://<host>/services/opentelekomcloud-docs/anti-ddos` opens
the page rather than a 404; and after the first discovery pass the log of that
run contains a line like `checked 84 repositories in opentelekomcloud-docs`.

## Local equivalent

`docker compose up --build` in the repository root runs the same backend with
a local PostgreSQL and the Vite dev server instead of the nginx image; see the
root README. The images themselves build locally with:

```bash
docker build -f Dockerfile.backend  --build-arg ARTIFACTORY_URL=$ARTIFACTORY_URL -t sdk-panel .
docker build -f Dockerfile.frontend --build-arg ARTIFACTORY_URL=$ARTIFACTORY_URL -t sdk-panel-frontend ./frontend
```
