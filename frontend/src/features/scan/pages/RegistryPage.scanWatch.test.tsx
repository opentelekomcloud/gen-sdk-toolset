import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderPage } from "../../../test/render";
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
 * A backend on which the job has already finished, but whose registry still
 * answered "scanning" the first time the page asked - exactly the moment the
 * page used to get stuck at until a reload.
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

beforeEach(() => {
  session.token = tokenWithRoles("worker");
});
afterEach(() => vi.unstubAllGlobals());

describe("a scanning row on the registry", () => {
  it("watches its job and refreshes the list once the job is done", async () => {
    const fetchMock = stubFinishedScan();

    renderPage(<RegistryPage />, { path: "/scan", route: "/scan" });

    // First answer: the row is scanning, and the row alone is what polls the job.
    expect(await screen.findByText(/job #7/)).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith(`/api/jobs/${JOB_ID}`))).toBe(true),
    );

    // The terminal edge refetched the list: the row now shows the scanned state,
    // with no page reload in between.
    expect(await screen.findByText("Scanned")).toBeInTheDocument();
    expect(screen.queryByText(/job #7/)).toBeNull();
  });
});
