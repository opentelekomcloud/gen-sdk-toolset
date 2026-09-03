/**
 * The roles Zitadel granted, read for rendering only.
 *
 * **This is not a security boundary.** The token is decoded here, never
 * verified: anyone can edit their own copy and hand themselves `worker`. What
 * that buys them is buttons - the backend validates the same token's signature
 * and refuses the request. Hiding a control a viewer cannot use is a courtesy,
 * `403` is the answer.
 */

/** Zitadel's project-roles claim, the same one the backend reads. */
export const PROJECT_ROLES_CLAIM = "urn:zitadel:iam:org:project:roles";

export type PanelRole = "worker" | "viewer";

const PANEL_ROLES: readonly PanelRole[] = ["worker", "viewer"];

/** May this session change panel state? Everything else is readable. */
export function canWrite(roles: readonly PanelRole[]): boolean {
  return roles.includes("worker");
}

/**
 * The panel roles carried by a JWT, ignoring any others.
 *
 * A malformed token yields no roles rather than an exception: the request that
 * follows will be refused by the backend anyway, and a parse error in a render
 * path would take the page down instead.
 */
export function rolesFromToken(token: string | null | undefined): PanelRole[] {
  const claims = decode(token);
  const granted = claims?.[PROJECT_ROLES_CLAIM];
  if (!granted || typeof granted !== "object" || Array.isArray(granted)) return [];
  return PANEL_ROLES.filter((role) => role in granted);
}

function decode(token: string | null | undefined): Record<string, unknown> | null {
  const payload = token?.split(".")[1];
  if (!payload) return null;
  try {
    /* base64url, and `atob` only reads base64: the padding and the two swapped
       characters are the whole difference between them. */
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "="));
    const claims: unknown = JSON.parse(json);
    return typeof claims === "object" && claims !== null
      ? (claims as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}
