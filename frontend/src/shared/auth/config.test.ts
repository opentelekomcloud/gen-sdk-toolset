import { afterEach, describe, expect, it, vi } from "vitest";

/* `config.ts` reads both sources once, at module load, so every case imports it
   fresh after arranging the window and the env. */
async function load() {
  vi.resetModules();
  return import("./config");
}

afterEach(() => {
  delete window.__PANEL_CONFIG__;
  vi.unstubAllEnvs();
});

describe("OIDC configuration", () => {
  it("reads the runtime config the container writes", async () => {
    window.__PANEL_CONFIG__ = {
      issuer: "https://runtime.zitadel.test",
      clientId: "1@runtime",
      scope: "openid urn:zitadel:iam:org:project:id:1:aud",
    };
    const { OIDC, isConfigured } = await load();
    expect(OIDC).toEqual({
      issuer: "https://runtime.zitadel.test",
      clientId: "1@runtime",
      scope: "openid urn:zitadel:iam:org:project:id:1:aud",
    });
    expect(isConfigured()).toBe(true);
  });

  it("prefers the runtime config over values inlined at build time", async () => {
    vi.stubEnv("VITE_ZITADEL_ISSUER", "https://build.zitadel.test");
    vi.stubEnv("VITE_ZITADEL_CLIENT_ID", "1@build");
    window.__PANEL_CONFIG__ = { issuer: "https://runtime.zitadel.test", clientId: "1@runtime" };
    const { OIDC } = await load();
    expect(OIDC.issuer).toBe("https://runtime.zitadel.test");
    expect(OIDC.clientId).toBe("1@runtime");
  });

  it("falls back to the build-time variables field by field", async () => {
    vi.stubEnv("VITE_ZITADEL_ISSUER", "https://build.zitadel.test");
    vi.stubEnv("VITE_ZITADEL_CLIENT_ID", "1@build");
    vi.stubEnv("VITE_ZITADEL_SCOPE", "openid profile");
    /* An empty runtime file - what the checked-in public/config.js contains. */
    window.__PANEL_CONFIG__ = {};
    const { OIDC, isConfigured } = await load();
    expect(OIDC).toEqual({
      issuer: "https://build.zitadel.test",
      clientId: "1@build",
      scope: "openid profile",
    });
    expect(isConfigured()).toBe(true);
  });

  it("is not configured when neither source names an issuer and a client id", async () => {
    vi.stubEnv("VITE_ZITADEL_ISSUER", "");
    vi.stubEnv("VITE_ZITADEL_CLIENT_ID", "");
    const { OIDC, isConfigured } = await load();
    expect(isConfigured()).toBe(false);
    expect(OIDC.scope).toBe("openid profile email");
  });
});
