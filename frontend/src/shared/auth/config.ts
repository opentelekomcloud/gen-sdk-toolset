/**
 * Where the Zitadel session comes from. Configured per deployment, never
 * hardcoded: the staging panel and a laptop talk to different instances, and a
 * client id baked into the source would make the build environment-specific.
 *
 * These are `VITE_` variables, read at build time - the same mechanism the
 * panel already used for its identity. A deployment that builds its own bundle
 * (staging/Dockerfile.frontend) sets them there.
 */
export const OIDC = {
  issuer: (import.meta.env.VITE_ZITADEL_ISSUER as string | undefined) ?? "",
  clientId: (import.meta.env.VITE_ZITADEL_CLIENT_ID as string | undefined) ?? "",
  /**
   * `openid profile email` identifies the user. A Zitadel project scope is what
   * makes the roles appear in the token at all, and it carries a project id, so
   * it is configuration rather than a constant - without it every session looks
   * role-less and the panel renders read-only for everybody.
   */
  scope:
    (import.meta.env.VITE_ZITADEL_SCOPE as string | undefined) ??
    "openid profile email",
} as const;

/** Whether signing in can even be attempted. */
export const isConfigured = (): boolean => Boolean(OIDC.issuer && OIDC.clientId);
