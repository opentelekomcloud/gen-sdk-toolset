import { PROJECT_ROLES_CLAIM, type PanelRole } from "../shared/auth/roles";

/**
 * A JWT carrying `claims`. Unsigned on purpose: the frontend decodes tokens and
 * never verifies them, so a real signature would prove nothing here.
 */
export function fakeToken(claims: Record<string, unknown>): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${encode({ alg: "RS256" })}.${encode(claims)}.signature-not-checked`;
}

/** A token for a session holding exactly these panel roles. */
export function tokenWithRoles(...roles: PanelRole[]): string {
  return fakeToken({
    sub: "user-1234",
    preferred_username: "ada@otc.test",
    [PROJECT_ROLES_CLAIM]: Object.fromEntries(roles.map((r) => [r, { "123": "otc.test" }])),
  });
}
