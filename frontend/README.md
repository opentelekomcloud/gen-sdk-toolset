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

## Signing in

The panel authenticates against Zitadel: the UI runs the authorization-code flow
with PKCE (a SPA application, no client secret), and every request to `/api`
carries the resulting access token. Configure the application in `.env` before
starting the dev server:

```bash
VITE_ZITADEL_ISSUER=https://your-instance.zitadel.cloud
VITE_ZITADEL_CLIENT_ID=123456789@your_project
VITE_ZITADEL_SCOPE=openid profile email urn:zitadel:iam:org:project:id:<project id>:aud
```

The project scope is not optional decoration: it is what puts this application's
roles into the token, and without it every session signs in successfully and then
looks role-less, which renders as a read-only panel. Vite inlines `VITE_*` at
build time, so a changed value needs the dev server restarted or the bundle
rebuilt. With nothing configured the panel says so instead of offering a sign-in
button that cannot work.

Two roles are granted in Zitadel and read from the token: `worker` may launch and
cancel scans, activate snapshots and exclude services; `viewer` may read. The UI
hides what a viewer cannot use, and the backend refuses it independently - the
hiding is a courtesy, the `403` is the boundary.

## Tests

`npm run test` runs Vitest in `jsdom`, so both kinds of test are available:
plain logic (the role rules, the API client, the cache helpers) and rendering
(`src/test/render.tsx` mounts a page with its providers and a seeded query
cache). The coverage gate stays scoped to the logic modules - see the note in
`vite.config.ts` for why.

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
