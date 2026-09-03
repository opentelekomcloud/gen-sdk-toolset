---
description: Rules for the FastAPI panel, its jobs and its schema
paths:
  - "src/tools/panel/**"
---

- **The ORM is not the domain model.** `DocumentRecord` stores the serialized
  IR in a JSONB `payload` column plus a handful of generated projection columns
  (`sa.Computed(...)`) for querying. It does not re-declare the domain shape as
  ORM fields. If you need to query by a domain field that is not projected yet,
  add a computed column - do not duplicate the model. Every table class carries
  a docstring explaining why it is shaped the way it is; write one for any new
  table.
- **Sessions are request-scoped** through `Depends(get_db)`. Background work
  opens its own session and does not borrow the request's.
- **Slow work happens outside a transaction.** The established shape: commit the
  job row *before* scheduling the task; in the runner, read what you need into
  local variables, commit the status change, let the session close, and only
  then call the provider. Reading an attribute after the commit will silently
  reopen a transaction and hold it across the network call.
- **Routes are authenticated by default.** `create_app` applies
  `Depends(require_viewer)` to the whole `/api` prefix, so a new route is closed
  the moment it is registered and only its *role* is a decision: a mutation adds
  `identity: Identity = Depends(require_worker)` and takes `initiated_by` from
  that identity, never from the request body. `/health` is the one open route.
- **Errors go through the envelope.** Raise `HTTPException`; the handlers in
  `api/errors.py` produce the `{"error": {"code", "message"}}` shape. Never
  assemble an error body by hand.
- **Lean on the database constraints instead of re-implementing them.** The
  partial unique index `uq_active_scan_job_per_service` is what makes "one
  active scan per service" true under concurrency - catch the `IntegrityError`
  and return `409`. A pre-check `SELECT` is a race, not a guard.
- **Migrations are append-only.** Never edit a committed revision. Autogenerate,
  then read the result: Alembic routinely misses CHECK constraints, partial
  indexes and enum changes, which is most of what this schema relies on.
- **Regenerate the schema** whenever routes or models change:
  `uv run panel openapi > src/tools/panel/openapi.json` (it prints to stdout, so
  the redirect is the command), then `cd frontend && npm run gen:types`. Commit
  both - the frontend types are generated from that file.
- **A job's terminal state is part of the contract.** If you add a failure path,
  it sets `status`, `finished_at` and `error` or `interruption`. A job that
  stops without a terminal transition is invisible to the UI, which will spin
  forever.
