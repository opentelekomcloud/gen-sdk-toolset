import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen } from "@testing-library/react";
import { renderPage } from "../../../test/render";
import { createQueryClient } from "../../../shared/api/queryClient";
import { tokenWithRoles } from "../../../test/token";
import type { ServiceListItem } from "../../../shared/api/types";
import { RegistryPage } from "./RegistryPage";

/** The session the mocked provider hands back. */
const session = vi.hoisted(() => ({ token: "" }));

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: session.token, profile: { preferred_username: "ada@otc.test" } },
    isAuthenticated: true,
    isLoading: false,
    signinRedirect: vi.fn(),
    signoutRedirect: vi.fn(),
  }),
}));

const NAME = "opentelekomcloud-docs/ecs";
const JOB_ID = 7;
/** The longest a visible tab may take to show a change saved on the server (ADR-0077). */
const DEADLINE_MS = 15_000;

/** The same service as the registry lists it, before and after the job. */
function listItem(scan_status: "scanning" | "scanned"): ServiceListItem {
  return {
    name: NAME,
    label: "ecs",
    scan_status,
    documents: 2,
    read_in_full: 2,
    docs_ok: 100,
    scanner_version: "0.1.0",
    scanned_at: "2026-08-01T10:00:00Z",
    docs_changed: false,
    rescan_reason: null,
    overall_breakdown: { ok: 2 },
    unread_breakdown: {},
    unread_documents: 0,
    rows_unrecognized: 0,
    section_rollup: {},
    error: null,
    error_at: null,
    job_id: scan_status === "scanning" ? JOB_ID : null,
    initiated_by: scan_status === "scanning" ? "ada@otc.test" : null,
  } as unknown as ServiceListItem;
}

const job = (status: "running" | "done") => ({
  id: JOB_ID,
  service_id: 1,
  repository: NAME,
  kind: "scan",
  status,
  scanner_version: null,
  commit_hash: null,
  error: null,
  created_at: "2026-08-01T10:00:00Z",
  started_at: null,
  finished_at: null,
});

/**
 * A backend on which the job finishes after the page has loaded: the registry
 * answers "scanning" the first time and "scanned" from then on. The job route
 * answers too, so a poll of it would succeed - the test checks none is made.
 */
function stubFinishedScan() {
  let listCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://panel.test");
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
    if (url.pathname === "/api/scan/services") {
      listCalls += 1;
      const item = listItem(listCalls === 1 ? "scanning" : "scanned");
      return json({ items: [item], counts: { all: 1 } });
    }
    if (url.pathname === `/api/jobs/${JOB_ID}`) return json(job("done"));
    if (url.pathname === "/api/scan/summary") {
      return json({ scanner_version: "0.1.0", services_total: 1, failed_services: 0, documents_total: 2, scans_running: 0 });
    }
    return json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Lets the clock run - each refetch fires and its answer lands - without waiting it out. */
const elapse = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers();
  session.token = tokenWithRoles("worker");
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("a scanning row on the registry", () => {
  it("shows the scan finished within the deadline, without polling the job (ADR-0085)", async () => {
    const fetchMock = stubFinishedScan();

    renderPage(<RegistryPage />, { path: "/scan", route: "/scan", client: createQueryClient() });
    await elapse(0);
    expect(screen.getByText(/job #7/)).toBeInTheDocument();

    // The periodic refetch of the list is what brings the finish, with no page
    // reload in between.
    await elapse(DEADLINE_MS);
    // The row's status pill, not the filter chip of the same name.
    expect(screen.getByText("Scanned", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText(/job #7/)).toBeNull();

    // The tab never asks for the job itself.
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/jobs/"))).toBe(false);
  });
});
