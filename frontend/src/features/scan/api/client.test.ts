import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, qs } from "./client";
import { bindSession, resetSession } from "../../../shared/auth/session";

const mockFetch = (impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) => {
  const spy = vi.fn(impl);
  vi.stubGlobal("fetch", spy);
  return spy;
};

afterEach(() => {
  vi.unstubAllGlobals();
  resetSession();
});

describe("apiFetch", () => {
  it("prefixes /api and parses JSON", async () => {
    const spy = mockFetch(async () => new Response(JSON.stringify({ a: 1 }), { status: 200 }));
    await expect(apiFetch<{ a: number }>("/scan/summary")).resolves.toEqual({ a: 1 });
    expect(spy.mock.calls[0][0]).toBe("/api/scan/summary");
  });

  it("always sends Content-Type, even when the caller passes headers", async () => {
    const spy = mockFetch(async () => new Response("{}", { status: 200 }));
    await apiFetch("/x", { method: "POST", headers: { "X-Extra": "1" } });
    const headers = new Headers(spy.mock.calls[0][1]!.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-Extra")).toBe("1");
  });

  it("merges Headers instances too, without clobbering a caller Content-Type", async () => {
    const spy = mockFetch(async () => new Response("{}", { status: 200 }));
    await apiFetch("/x", { method: "POST", headers: new Headers({ "Content-Type": "text/plain" }) });
    const headers = new Headers(spy.mock.calls[0][1]!.headers);
    expect(headers.get("Content-Type")).toBe("text/plain");
  });

  it("returns undefined for 204", async () => {
    mockFetch(async () => new Response(null, { status: 204 }));
    await expect(apiFetch<void>("/x", { method: "POST" })).resolves.toBeUndefined();
  });

  it("throws ApiError with code/message from the error envelope", async () => {
    mockFetch(
      async () =>
        new Response(JSON.stringify({ error: { code: "already_scanning", message: "Job running" } }), { status: 409 }),
    );
    const err = await apiFetch("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "already_scanning", message: "Job running" });
  });

  it("falls back to statusText for non-JSON error bodies", async () => {
    mockFetch(async () => new Response("<html>gateway</html>", { status: 502, statusText: "Bad Gateway" }));
    const err = await apiFetch("/x").catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 502, code: "unknown", message: "Bad Gateway" });
  });
});

describe("qs", () => {
  it("serializes defined params", () => {
    expect(qs({ status: "failed", page: 2 })).toBe("?status=failed&page=2");
  });

  it("drops undefined and empty values", () => {
    expect(qs({ q: "", rule: undefined, sort: "name" })).toBe("?sort=name");
  });

  it("returns an empty string when nothing remains", () => {
    expect(qs({ q: "", x: undefined })).toBe("");
  });

  it("URL-encodes values", () => {
    expect(qs({ q: "a b&c" })).toBe("?q=a+b%26c");
  });
});

describe("apiFetch and the session", () => {
  it("sends the access token as a bearer credential", async () => {
    const spy = mockFetch(async () => new Response("{}", { status: 200 }));
    bindSession({ accessToken: () => "token-abc", unauthenticated: () => {} });

    await apiFetch("/scan/summary");

    expect(new Headers(spy.mock.calls[0][1]!.headers).get("Authorization")).toBe(
      "Bearer token-abc",
    );
  });

  it("sends no Authorization header while nobody is signed in", async () => {
    const spy = mockFetch(async () => new Response("{}", { status: 200 }));

    await apiFetch("/scan/summary");

    expect(new Headers(spy.mock.calls[0][1]!.headers).has("Authorization")).toBe(false);
  });

  it("sends the session back to sign in when the panel answers 401", async () => {
    mockFetch(
      async () =>
        new Response(JSON.stringify({ error: { code: "unauthenticated", message: "expired" } }), {
          status: 401,
        }),
    );
    const signin = vi.fn();
    bindSession({ accessToken: () => "stale-token", unauthenticated: signin });

    // The error still propagates: nothing may render as if this had succeeded.
    await expect(apiFetch("/scan/summary")).rejects.toBeInstanceOf(ApiError);
    expect(signin).toHaveBeenCalledOnce();
  });

  it("does not send a 403 back to sign in - that session is valid, just not allowed", async () => {
    mockFetch(
      async () =>
        new Response(JSON.stringify({ error: { code: "forbidden", message: "needs worker" } }), {
          status: 403,
        }),
    );
    const signin = vi.fn();
    bindSession({ accessToken: () => "good-token", unauthenticated: signin });

    await expect(apiFetch("/scan/summary")).rejects.toMatchObject({ status: 403 });
    expect(signin).not.toHaveBeenCalled();
  });

  it("redirects once however many queries are refused together", async () => {
    // A page holds several queries and they fail as a group; each one calling
    // signinRedirect would stack navigations on top of each other.
    mockFetch(async () => new Response("{}", { status: 401 }));
    const signin = vi.fn();
    bindSession({ accessToken: () => "stale-token", unauthenticated: signin });

    await Promise.allSettled([
      apiFetch("/scan/summary"),
      apiFetch("/scan/services"),
      apiFetch("/scan/attention"),
    ]);

    expect(signin).toHaveBeenCalledOnce();
  });
});
