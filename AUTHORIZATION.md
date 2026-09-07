# Authentication and authorization

The panel authenticates every person against Zitadel and knows two roles.
There is no other door: no shared password, no anonymous read, no API key.
This document is what an operator needs to set up in Zitadel and what the
panel does with the result. Deployment settings are in
[DEPLOYMENT.md](DEPLOYMENT.md).

## Roles

| Role | May |
|---|---|
| `viewer` | read everything: the registry, every service, every snapshot, exports |
| `worker` | everything a viewer may, plus launch and cancel scans, activate a snapshot, exclude and include services |

A signed-in account with neither role is refused: the UI explains that the
account has no access to this panel, the API answers `401`. A `viewer` who
sends a state-changing request gets `403`; the UI does not show those controls
to a viewer in the first place, but the `403` is the boundary, the hiding is a
courtesy.

Every state change is attributed to the signed-in identity - `initiated_by`
on a scan job, `excluded_by` on an exclusion - taken from Zitadel, never from
the request.

## What to create in Zitadel

One **project**, with:

1. **Roles** `worker` and `viewer` (the keys must be exactly these).
   Enable *Assert roles on authentication* on the project, so that granted
   roles are put into the tokens the project's applications receive.
2. An **API application** (type API, authentication method *JWT* or *Basic*
   - the panel never uses its credentials; the application exists so that the
   panel has an audience to validate against). Its client id is the backend's
   `AUTH__AUDIENCE`.
3. A **user agent (SPA) application**, authentication method *PKCE*, grant
   type *authorization code*, with:
   - redirect URI: the panel's public URL, e.g. `https://panel.example.com`
     (add `http://localhost:5173` for local development if wanted);
   - post-logout redirect URI: the same URL;
   - refresh tokens on, if the silent renew should use them (otherwise the UI
     renews through a hidden iframe against the redirect URI, which also
     works).
   Its client id is the frontend's `ZITADEL_CLIENT_ID`.

Then grant users the `viewer` or `worker` role on the project (an
*authorization* in Zitadel's terms). A user needs one of the two; `worker`
implies everything `viewer` may do, there is no need to grant both.

The frontend's `ZITADEL_SCOPE` must contain the project's audience scope,
`urn:zitadel:iam:org:project:id:<project id>:aud`, next to
`openid profile email`. That scope is what makes Zitadel put the project
roles into the access token; without it every sign-in succeeds and every
session looks role-less.

## What the backend checks

For every request outside `/health`:

- a bearer token is present; otherwise `401` with a `WWW-Authenticate`
  challenge;
- it is signed by the issuer's current keys (`<AUTH__ISSUER>/oauth/v2/keys`,
  fetched on first use, cached, refetched once on an unknown key id - a key
  rotation needs no restart) with RS256, not with whatever algorithm the token
  names;
- `exp` and `sub` are present and `exp` is in the future;
- the audience contains `AUTH__AUDIENCE`;
- the claim `urn:zitadel:iam:org:project:roles` names `viewer` or `worker`;
  otherwise `401`.

Worker-only routes additionally require `worker`; otherwise `403`. The
operator's name is read from the token when a claim carries it and from
`<AUTH__ISSUER>/oidc/v1/userinfo` otherwise, cached for fifteen minutes; when
that endpoint is unreachable the numeric subject is recorded and the log says
so.

Tokens are validated per request; there is no server-side session and nothing
to invalidate on the panel. Revoking a person's access is done in Zitadel by
removing the role or the user, and takes effect when their current token
expires (Zitadel's default access token lifetime is 12 hours; shorten it on
the project if that is too long).

## What the frontend does

Authorization code flow with PKCE, no client secret. The access token is
attached to every `/api` request; a `401` from the API sends the user back
through Zitadel; the token is renewed silently before it expires. The UI reads
the roles from the token only to decide which controls to render.

## Checking a deployment

1. `curl https://<host>/api/scan/summary` without a token answers `401`.
2. A user with only `viewer` signs in and sees the panel with no rescan,
   activate or exclude controls.
3. A user with `worker` signs in and sees the panel with rescan,
   activate or exclude controls.
4. A user with no role on the project signs in and is told the account has no
   access, with a sign-out button.

If every account, including a worker, lands in case 4: the scope is missing
the project audience, or *Assert roles on authentication* is off.
If sign-in never returns to the panel: the redirect URI in the SPA application
does not match the panel's URL exactly (scheme, host, port, trailing slash).
If `/api` answers `500` for everyone: `AUTH__ISSUER` or `AUTH__AUDIENCE` is
unset on the backend.
