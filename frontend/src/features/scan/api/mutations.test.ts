import { MutationObserver, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { rescanMutation, useActivateSnapshot, useExclude, useInclude } from "./mutations";
import { keys } from "./queries";
import { bindSession, resetSession } from "../../../shared/auth/session";
import type { ServiceDetail } from "../../../shared/api/types";

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({ user: { access_token: "", profile: { preferred_username: "ada@otc.test" } } }),
}));

const NAME = "opentelekomcloud-docs/ecs";

/** Only the fields the optimistic flip touches; the rest never enters this path. */
const SERVICE = {
  name: NAME,
  scan_status: "scanned",
  initiated_by: null,
  job_id: undefined,
  started_at: undefined,
} as unknown as ServiceDetail;

const respond = (status: number, body: unknown) =>
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );

afterEach(() => {
  vi.unstubAllGlobals();
  resetSession();
});

/** Runs the real mutation lifecycle - no React, no DOM. */
async function rescan(qc: QueryClient) {
  const observer = new MutationObserver(qc, rescanMutation(qc, NAME, "ada@otc.test"));
  return observer.mutate().catch(() => undefined);
}

describe("rescanMutation: the optimistic flip and what undoes it", () => {
  it("shows the service as scanning by the signed-in user before the server answers", async () => {
    const qc = new QueryClient();
    qc.setQueryData(keys.service(NAME), SERVICE);
    respond(202, { job_id: 7 });

    await rescan(qc);

    const after = qc.getQueryData<ServiceDetail>(keys.service(NAME));
    expect(after?.scan_status).toBe("scanning");
    expect(after?.initiated_by).toBe("ada@otc.test");
  });

  it("marks the attention band stale the moment the scan is accepted", async () => {
    // A failed service stops counting as failed as soon as its new job is the
    // last one, so the band changes at scan start - not only at scan end.
    const qc = new QueryClient();
    qc.setQueryData(keys.service(NAME), SERVICE);
    qc.setQueryData(keys.attention, [{ code: "failed", panel: "scan", label: "Failed", count: 1 }]);
    respond(202, { job_id: 7 });

    await rescan(qc);

    expect(qc.getQueryState(keys.attention)?.isInvalidated).toBe(true);
  });

  it("rolls the flip back when the panel refuses the caller", async () => {
    // 403 is what a viewer gets: the request never reached a scan, so the row
    // must not be left claiming one is running.
    const qc = new QueryClient();
    qc.setQueryData(keys.service(NAME), SERVICE);
    respond(403, { error: { code: "forbidden", message: "This action requires the worker role" } });

    await rescan(qc);

    expect(qc.getQueryData<ServiceDetail>(keys.service(NAME))).toEqual(SERVICE);
  });

  it("rolls back for any refusal, not just the one it expected", async () => {
    const qc = new QueryClient();
    qc.setQueryData(keys.service(NAME), SERVICE);
    respond(409, { error: { code: "conflict", message: "already scanning" } });

    await rescan(qc);

    expect(qc.getQueryData<ServiceDetail>(keys.service(NAME))).toEqual(SERVICE);
  });

  it("sends the session's name, which the backend then ignores in favour of the token", async () => {
    const qc = new QueryClient();
    bindSession({ accessToken: () => "token-abc", unauthenticated: () => {} });
    respond(202, { job_id: 1 });

    await rescan(qc);

    const [, init] = (globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } })
      .mock.calls[0];
    expect(JSON.parse(String(init.body))).toEqual({ initiated_by: "ada@otc.test" });
  });
});

describe("the changes to Scan data the Generation list follows", () => {
  /** Runs one of the hooks against a cache holding the Generation list. */
  function hookWithList<T>(useHook: (name: string) => T) {
    const qc = new QueryClient();
    qc.setQueryData(keys.genList({ q: "" }), [{ name: "opentelekomcloud-docs/vpc", label: "vpc" }]);
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: qc }, children);
    const { result } = renderHook(() => useHook(NAME), { wrapper });
    const listInvalidated = () => qc.getQueryState(keys.genList({ q: "" }))?.isInvalidated;
    return { qc, result, listInvalidated };
  }

  it("marks the list stale after a snapshot activation", async () => {
    const { result, listInvalidated } = hookWithList(useActivateSnapshot);
    respond(200, { items: [], active_id: 2, latest_id: 2 });

    await result.current.mutateAsync(2);

    expect(listInvalidated()).toBe(true);
  });

  it("marks the list stale after an exclusion", async () => {
    const { result, listInvalidated } = hookWithList(useExclude);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));

    await result.current.mutateAsync("retired");

    expect(listInvalidated()).toBe(true);
  });

  it("marks the list stale after an exclusion is undone, without adding the service itself", async () => {
    // Whether the restored service belongs on the list is the backend's answer
    // (ADR-0043): the cache keeps what it had until that answer arrives.
    const { qc, result, listInvalidated } = hookWithList(useInclude);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));

    await result.current.mutateAsync();

    expect(listInvalidated()).toBe(true);
    expect(qc.getQueryData(keys.genList({ q: "" }))).toEqual([{ name: "opentelekomcloud-docs/vpc", label: "vpc" }]);
  });
});
