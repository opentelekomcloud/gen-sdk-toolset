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

`.npmrc` in this directory names the registry and holds no secret. The token
goes into your **user-level** npm config, once:

1. Log in at <https://artifactory.devops.telekom.de/ui/login/>, open your
   profile and generate an identity token.
2. Store it - the prompt hides what you paste:

   ```bash
   read -s "T?Paste token: " && npm config set --location=user "//artifactory.devops.telekom.de/artifactory/api/npm/one-design-system-npm/:_authToken" "$T"; unset T
   chmod 600 ~/.npmrc
   ```

After that `npm install` and `npm ci` work as usual, and `docker compose`
passes the same `~/.npmrc` into the image build as a secret. Never put the
token into `frontend/.npmrc` - it is committed, and this repository is public.

CI needs no token of its own: the workflows log in with the organization's
JFrog service account (`ARTIFACTORY_AUTH_USERNAME` / `ARTIFACTORY_AUTH_PASSWORD`,
the secrets the Docker builds already use), which can read the ODS registry like
any signed-in JFrog user. Pull requests from forks get no secrets, so their
frontend jobs cannot install the packages.

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
