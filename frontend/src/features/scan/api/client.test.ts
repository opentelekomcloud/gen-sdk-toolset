import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, qs } from "./client";

const mockFetch = (impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) => {
  const spy = vi.fn(impl);
  vi.stubGlobal("fetch", spy);
  return spy;
};

afterEach(() => vi.unstubAllGlobals());

describe("apiFetch", () => {
  it("prefixes /api and parses JSON", async () => {
    const spy = mockFetch(async () => new Response(JSON.stringify({ a: 1 }), { status: 200 }));
    await expect(apiFetch<{ a: number }>("/scan/summary")).resolves.toEqual({ a: 1 });
    expect(spy.mock.calls[0][0]).toBe("/api/scan/summary");
  });

  it("always sends Content-Type, even when the caller passes headers", async () => {
    const spy = mockFetch(async () => new Response("{}", { status: 200 }));
    await apiFetch("/x", { method: "POST", headers: { "X-Extra": "1" } });
    const init = spy.mock.calls[0][1]!;
    expect(init.headers).toMatchObject({ "Content-Type": "application/json", "X-Extra": "1" });
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
