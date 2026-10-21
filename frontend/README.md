# Frontend

React + TypeScript + Vite frontend for the scan panel.

## Local development

Requires Node 22+ and a token for the ODS packages (next section). Run from
this `frontend/` directory:

```bash
npm install
npm run dev
```

The dev server starts on `http://localhost:5173` and proxies API requests
to the backend at `http://127.0.0.1:8000` (start the backend separately —
see the root README).

## ODS packages

The UI is built on ODS, the OneExperience Design System (issue #135):
`@telekom-ods/react-ui-kit`, `@telekom-ods/design-tokens` and
`@telekom-ods/react-icons`. They live in the Telekom Artifactory npm registry,
which needs a token.

`.npmrc` in this directory names the registry and reads the token from the
`ODS_NPM_TOKEN` environment variable. Never put the token itself there - the
file is committed, and this repository is public.

Get a token once: log in at <https://artifactory.devops.telekom.de/ui/login/>,
open your profile and generate an identity token, then put it into the root
`.env` as `ODS_NPM_TOKEN=<token>`. Docker Compose hands it to the frontend
image build as a secret; the image keeps no copy.

npm itself does not read `.env`, so an install on the host needs
`ODS_NPM_TOKEN` in the environment of that `npm install` / `npm ci`. Only
installing needs it: `lint`, `build`, `test` and `dev` work from
`node_modules` and never contact the registry. The checks also run in the dev
container, with nothing installed on the host - see "Checks".

CI needs no token of its own: the workflows pass the organization's JFrog
service account secret `ARTIFACTORY_AUTH_PASSWORD` - an identity token, the one
the Docker builds already log in with - as `ODS_NPM_TOKEN`. Pull requests from
forks get no secrets, so their frontend jobs cannot install the packages.

**How the UI uses ODS.** `src/main.tsx` loads the fonts, tokens and component
styles; `data-scheme` and `data-mode` on `<body>` drive the colours, and the
header's light/dark switch sets `data-mode`. `src/index.css` maps Tailwind's
colours onto the ODS tokens - use `bg-surface`, `text-ink`, `text-success`,
`neutral-*` and so on; the Tailwind palette (`gray-*`, `red-*`, …) is switched
off and `src/theme.test.ts` fails on it. Use the ODS component where one fits
(`ODSButton`, `ODSInlineNotification`, `ODSDialog`, …) and its icons from
`@telekom-ods/react-icons`; `src/shared/ui/` holds the few helpers for what
ODS 3.0.1 does not cover (text fields, router links drawn as buttons).

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
build time, so a changed value needs the dev server restarted. With nothing
configured the panel says so instead of offering a sign-in button that cannot
work.

The deployed image (`../Dockerfile.frontend`) bakes nothing in. It serves the
bundle from nginx on port 8080 and writes `/config.js` at container start from
`ZITADEL_ISSUER`, `ZITADEL_CLIENT_ID` and `ZITADEL_SCOPE`; the app reads that
file before the `VITE_*` fallback (`src/shared/auth/config.ts`). One image, any
deployment - changing the Zitadel application is a restart, not a rebuild.
`/api` is not served by that image: the ingress in front routes it to the
backend.

Two roles are granted in Zitadel and read from the token: `worker` may launch and
cancel scans, activate snapshots and exclude services; `viewer` may read. The UI
hides what a viewer cannot use, and the backend refuses it independently - the
hiding is a courtesy, the `403` is the boundary.

## Checks

Lint, typecheck with build, and the tests with their coverage gate - the three
the `frontend` CI job runs and the Definition of Done in `../AGENTS.md` asks
for. Either place works.

**In the dev container**, from the repository root. It needs only
`ODS_NPM_TOKEN` in the root `.env`; nothing is installed on the host:

```bash
docker compose -f docker-compose.dev.yml run --rm --no-deps frontend sh -c "npm run lint && npm run build && npm run test:coverage"
```

The first run builds the image. After `package.json` or `package-lock.json`
changes, rebuild it with
`docker compose -f docker-compose.dev.yml build frontend` - the container's
`node_modules` comes from the image, not from your checkout. `dist/` and
`coverage/` land in this directory as usual.

**On the host**, from this `frontend/` directory, once `node_modules` is
installed (see "ODS packages"):

```bash
npm run lint && npm run build && npm run test:coverage
```

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
