import { describe, expect, it } from "vitest";
import { PROJECT_ROLES_CLAIM, canWrite, rolesFromToken } from "./roles";

/** A JWT with `claims` as its payload. Unsigned: nothing here verifies it, and
 *  that is the point of the module under test. */
function token(claims: Record<string, unknown>): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${encode({ alg: "RS256" })}.${encode(claims)}.signature-not-checked`;
}

describe("rolesFromToken: what Zitadel granted this session", () => {
  it("reads the project-roles claim", () => {
    const granted = { worker: { "123": "otc.test" }, viewer: { "123": "otc.test" } };
    expect(rolesFromToken(token({ [PROJECT_ROLES_CLAIM]: granted }))).toEqual([
      "worker",
      "viewer",
    ]);
  });

  it("ignores roles that belong to another application", () => {
    const granted = { "some-other-app-admin": { "123": "otc.test" }, viewer: {} };
    expect(rolesFromToken(token({ [PROJECT_ROLES_CLAIM]: granted }))).toEqual(["viewer"]);
  });

  it("grants nothing for a token that carries no roles at all", () => {
    expect(rolesFromToken(token({ sub: "user-1" }))).toEqual([]);
  });

  it("grants nothing rather than throwing on a token it cannot read", () => {
    // A parse error in a render path would take the page down; the request that
    // follows is refused by the backend either way.
    expect(rolesFromToken(token({ [PROJECT_ROLES_CLAIM]: "worker" }))).toEqual([]);
    expect(rolesFromToken("not-a-jwt")).toEqual([]);
    expect(rolesFromToken("header.%%%not-base64%%%.sig")).toEqual([]);
    expect(rolesFromToken(`header.${btoa("42")}.sig`)).toEqual([]); // valid JSON, not claims
    expect(rolesFromToken(null)).toEqual([]);
    expect(rolesFromToken(undefined)).toEqual([]);
  });
});

describe("canWrite: which sessions get the controls", () => {
  it("is the worker role and nothing else", () => {
    expect(canWrite(["worker"])).toBe(true);
    expect(canWrite(["worker", "viewer"])).toBe(true);
    expect(canWrite(["viewer"])).toBe(false);
    expect(canWrite([])).toBe(false);
  });
});
