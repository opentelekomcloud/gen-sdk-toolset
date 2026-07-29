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
# a dump of the local panel database (services, generations, documents)
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

`GITHUB_TOKEN` is deliberately not set. Reading the panel does not need it; a
scan launched on this host would spend the quota of whatever token lives here,
so scanning stays a laptop activity unless you decide otherwise (uncomment the
line in `docker-compose.staging.yml`).

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
