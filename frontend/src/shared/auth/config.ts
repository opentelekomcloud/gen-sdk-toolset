/**
 * Where the Zitadel session comes from. Configured per deployment, never
 * hardcoded: a deployed panel and a laptop talk to different instances, and a
 * client id baked into the source would make the build environment-specific.
 *
 * Two sources, in this order:
 *
 * 1. `window.__PANEL_CONFIG__`, written by `/config.js` - a file the container
 *    generates from its environment at start (`frontend/docker/`). This is what
 *    lets one built image serve any deployment: the bundle is the same, only
 *    the file next to it changes.
 * 2. `VITE_*` variables, inlined by Vite at build time. The dev server path -
 *    `npm run dev` reads them from `.env` - and the fallback when nobody wrote
 *    a `config.js` (the checked-in `public/config.js` is empty on purpose).
 */
export type PanelConfig = {
  issuer?: string;
  clientId?: string;
  scope?: string;
};

declare global {
  interface Window {
    __PANEL_CONFIG__?: PanelConfig;
  }
}

const runtime: PanelConfig = window.__PANEL_CONFIG__ ?? {};

export const OIDC = {
  issuer: runtime.issuer || (import.meta.env.VITE_ZITADEL_ISSUER as string | undefined) || "",
  clientId:
    runtime.clientId || (import.meta.env.VITE_ZITADEL_CLIENT_ID as string | undefined) || "",
  /**
   * `openid profile email` identifies the user. A Zitadel project scope is what
   * makes the roles appear in the token at all, and it carries a project id, so
   * it is configuration rather than a constant - without it every session looks
   * role-less and the panel renders read-only for everybody.
   */
  scope:
    runtime.scope ||
    (import.meta.env.VITE_ZITADEL_SCOPE as string | undefined) ||
    "openid profile email",
} as const;

/** Whether signing in can even be attempted. */
export const isConfigured = (): boolean => Boolean(OIDC.issuer && OIDC.clientId);
