# Web panel

Control panel for the SDK generation toolset.

Stack: FastAPI · SQLAlchemy 2.0 · Alembic · SQLite.

## Database (local)

The connection string defaults to a local SQLite file (`panel.db`) and can be
overridden via `DATABASE__URL` (env or `.env`).

Apply migrations from the repository root:

```bash
uv run alembic upgrade head
```

On a fresh database this creates all four tables (`job`, `service`,
`document`, `issue`). The SQLite file is created automatically on first run.

### Useful commands

```bash
uv run alembic current                 # show current revision
uv run alembic downgrade -1            # roll back the last migration
uv run alembic revision --autogenerate -m "message"   # new migration after model changes
uv sync --extra panel                  # add dependencies
```

## Running the dev server

From the project root, with `.env` present (must include `GITHUB_TOKEN`):

```bash
uv run uvicorn tools.panel.api.app:create_app --factory --reload
```

The API starts on `http://127.0.0.1:8000`.

- Health check: `GET http://127.0.0.1:8000/health` → `{"status": "ok"}`
- Everything else needs a bearer token; `/health` is the only open route.

Swagger UI and `/openapi.json` are not served: they sat outside `/api`, where
the token requirement does not reach, so a deployed panel would have handed its
API surface to anyone. Read the committed `openapi.json` instead - it is
regenerated below and CI fails when it drifts.

## Regenerating the OpenAPI schema

The committed schema at `src/tools/panel/openapi.json` is the API contract
consumed by the frontend type generator. It does **not** require a running
server. Regenerate it after any change to the API and commit the result:

```bash
uv run panel openapi | Out-File -Encoding utf8 src/tools/panel/openapi.json
```