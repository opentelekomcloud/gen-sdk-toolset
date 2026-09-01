# Staging the scan panel

A single host with Docker: Caddy terminates TLS and asks for a password, the
FastAPI backend serves `/api`, PostgreSQL arrives with the data from a local
scan run. Nothing but Caddy is published.

## What the host needs

- Docker with the compose plugin.
- Inbound `22` from your addresses; `80` and `443` from wherever the panel has
  to be reachable. Nothing else - the database and the backend are not exposed.
- A DNS record pointing at the host **if** you want a real certificate. Without
  one the panel runs on `http://<EIP>`, and a basic-auth password then travels
  in clear text: use a throwaway password and rotate it after the demo.

## 1. Copy the project and the data

From the laptop that holds the scanned database:

```bash
# a dump of the local panel database (services, snapshots, documents)
docker exec gen_sdk_tooling-db-1 pg_dump -U panel -d panel --no-owner --no-privileges \
  | gzip -9 > panel.sql.gz

scp -r <project> panel.sql.gz ubuntu@<EIP>:~/
ssh ubuntu@<EIP> 'mkdir -p ~/gen_sdk_tooling/deploy/seed && mv ~/panel.sql.gz ~/gen_sdk_tooling/deploy/seed/'
```

The dump lands in `deploy/seed/`, which PostgreSQL restores **once**, when its
data directory is still empty. Re-running compose later does not touch it; to
reload the data, remove the `pgdata` volume first.

## 2. Configure

On the host, in `deploy/.env`:

```bash
POSTGRES_PASSWORD=<a fresh password>
SITE_ADDRESS=panel.example.com     # or ":80" when there is no DNS name
SITE_URL=https://panel.example.com # or "http://<EIP>"
PANEL_USER=<login>
PANEL_PASSWORD_HASH=<bcrypt hash>
```

Generate the hash yourself - it never has to leave your machine:

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext '<password>'
```

The backend gets no `GITHUB_TOKEN`. Reading the panel does not need one, and a
scan launched on this host would spend the quota of whatever token lived there,
so scanning stays a laptop activity unless you decide otherwise (uncomment the
line in `docker-compose.staging.yml`). Set `GITHUB_TOKEN` anyway if you want the
scheduled registry refresh below: only the discovery container reads it, and
that pass starts no scan.

## 3. Start

```bash
cd ~/gen_sdk_tooling/deploy
docker compose -f docker-compose.staging.yml up -d --build
docker compose -f docker-compose.staging.yml logs -f web
```

The first start builds the frontend bundle and restores the dump; give it a few
minutes. With a domain, Caddy obtains a certificate on its own - the log line
to wait for names the certificate.

## 4. Check

```bash
curl -u '<login>:<password>' https://panel.example.com/api/scan/summary
curl -s -o /dev/null -w '%{http_code}\n' https://panel.example.com/api/scan/summary  # expect 401
```

The second command is the one that matters: without credentials everything,
including `POST /api/scan/services/{repo}/rescan`, must answer `401`.

## The API contract

`/docs` (Swagger UI), `/redoc` and `/openapi.json` are proxied to the backend
and guarded by the same password as the panel. "Try it out" issues real
requests: a rescan started from there creates a real job, which fails on this
host because no GitHub token is configured - the failure is recorded on the
job, as any other failure would be.

## Signing in

The panel authenticates against Zitadel, and both halves need configuring: the
backend validates tokens (`AUTH__ISSUER`, `AUTH__AUDIENCE`) and the UI runs the
login flow (`VITE_ZITADEL_ISSUER`, `VITE_ZITADEL_CLIENT_ID`, `VITE_ZITADEL_SCOPE`).
Set all five in `.env`, then rebuild - the UI values are inlined into the bundle
at build time, so `up -d --build` is what applies a change to them.

In Zitadel: one project with the roles `worker` and `viewer`, an API application
whose client id is the backend's `AUTH__AUDIENCE`, and a user-agent (SPA)
application with PKCE whose client id is `VITE_ZITADEL_CLIENT_ID` and whose
redirect URI is this panel's `SITE_URL`.

Caddy's shared password is now a second door rather than the only one. It still
guards `/docs` and anything else outside `/api`, which the panel does not
authenticate itself.

## Keeping the registry current

Discovery is the only thing that runs on a schedule. One pass registers
repositories that appeared in the organization, refreshes `eligibility_checked_at`,
and re-reads each eligible repository's branch HEAD - which is what every drift
mark on the panel is compared against. **It never starts a scan.** Which snapshot
the panel serves changes only when someone asks for it.

One pass, on the terminal:

```bash
docker compose -f docker-compose.staging.yml --profile sync run --rm discovery
```

The `sync` profile keeps it out of `up`, and the service runs the image the
backend is already running - so the stack has to be up (step 3), there is
nothing extra to build, and `up -d --build` refreshes what the sync executes
along with the panel. `GITHUB_TOKEN` in `.env` reaches this container and no
other: the sync can read GitHub while a rescan started from the UI on this host
still cannot.

To run it every four hours, `crontab -e` on the host:

```cron
17 */4 * * * cd ~/gen_sdk_tooling/deploy && { date -u -Is; docker compose -f docker-compose.staging.yml --profile sync run --rm -T discovery; } >> discovery.log 2>&1
```

That line is the whole mechanism, and the interval lives in it - change it here
and nowhere else. `-T` because cron has no terminal, `date` because the summary
carries no timestamp of its own, and off the hour because nothing here needs to
be the first job on the machine to wake up. Every few hours is enough:
documentation does not move faster than that, and each pass spends a request per
repository.

### Reading the log

Each pass appends to `discovery.log` next to the stack:

```
2026-08-26T04:17:03+00:00
checked 84 repositories in opentelekomcloud-docs: 71 with api-ref/source, 13 without (0 new, 84 already registered)
branch HEAD refreshed for 71 of 71 eligible repositories
```

Those counters are the point of the log. `0 new` every time is normal; `refreshed
for 0 of 71` is not - it means the marks the panel is showing are as old as the
last pass that did resolve them.

A rate limit or a bad token stops the pass where it is, keeps everything already
written, and exits non-zero with the reason. Nothing retries: the next scheduled
run finishes the work. A pass that fails every time is a configuration problem,
and the log says which.

The file grows by a handful of lines per pass and nothing rotates it - hand it to
`logrotate` if this host outlives the demo.

## Updating the data later

```bash
docker compose -f docker-compose.staging.yml down
docker volume rm deploy_pgdata
# put a fresh panel.sql.gz into deploy/seed/
docker compose -f docker-compose.staging.yml up -d --build
```

## What this deployment is not

- **No user accounts.** One shared password guards the whole panel; the
  `initiated_by` field on a job is still self-reported by the frontend.
- **No backups.** The data is a copy of a laptop run; the source of truth is
  whatever machine did the scanning.
- **No migrations on a live database.** The backend applies Alembic migrations
  at startup, which is fine for a restored dump and for a demo, and is not a
  scheme for a database anyone depends on.
