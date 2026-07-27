## What this changes

<!-- Group by theme. One short paragraph per group, then the files it touches,
     each with a sentence on what that file is responsible for now.
     Mark new and moved files with **[NEW]** / **[MOVED]**. -->

## Why

<!-- The problem, and why this shape rather than the obvious alternative. -->

## Contract changes

<!-- Delete if none. Tick what moved and say what consumers must do. -->

- [ ] Serialized IR or scan models (`DOCUMENT_SCHEMA_VERSION`)
- [ ] Report contract (`REPORT_SCHEMA_VERSION`)
- [ ] Panel routes or schemas — `openapi.json` + `schema.gen.ts` regenerated and committed
- [ ] Database schema — new Alembic revision, no committed revision edited
- [ ] New vocabulary recorded in `docs/GLOSSARY.md`

## Checks

<!-- Tick only what you actually ran. An unticked box is information. -->

- [ ] `ruff check .` and `ruff format --check .`
- [ ] `lint-imports`
- [ ] `uv run pytest` green
- [ ] Diff coverage ≥ 80%, total ≥ 75%
- [ ] Frontend: `npm run lint && npm run build && npm run test:coverage`
- [ ] New status or issue code has a test that actually produces it
