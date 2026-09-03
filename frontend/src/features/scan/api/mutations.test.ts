import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { rescanMutation } from "./mutations";
import { keys } from "./queries";
import { bindSession, resetSession } from "../../../shared/auth/session";
import type { ServiceDetail } from "../../../shared/api/types";

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
