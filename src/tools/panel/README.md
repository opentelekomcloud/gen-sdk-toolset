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
```
