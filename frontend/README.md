# Frontend

React + TypeScript + Vite frontend for the scan panel.

## Local development

Requires Node 22+. Run from this `frontend/` directory:

```bash
npm install
npm run dev
```

The dev server starts on `http://localhost:5173` and proxies API requests
to the backend at `http://127.0.0.1:8000` (start the backend separately —
see the root README).

## Generating API types

Types in `src/shared/api/schema.gen.ts` are generated from the backend's
committed OpenAPI schema (`../src/tools/panel/openapi.json`), not a live server:

```bash
npm run gen:types
```

Re-run after the backend API changes. The generated file is not edited by hand.

Components do not import it directly: `src/shared/api/types.ts` aliases the
schemas under the names the UI uses (`Snapshot`, `ServiceDetail`, `Job`), so a
field that changes shape breaks the build at the component that reads it. The
few shapes the schema cannot express - view models, and narrowings of fields the
backend types as `str` - live in `src/features/scan/types.ts` and say why.
