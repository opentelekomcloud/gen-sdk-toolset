import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderPage, stubEmptyApi } from "../../../test/render";
import { tokenWithRoles } from "../../../test/token";
import { keys } from "../api/queries";
import type { ServiceDetail } from "../../../shared/api/types";
import { ServicePage } from "./ServicePage";
import { Header } from "../../../components/Header";

/** The session the mocked provider hands back; each test sets the roles. */
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

/** Enough of a service for the page to render its controls. */
const SERVICE = {
  name: NAME,
  label: "ecs",
  scan_status: "scanned",
  documents: 2,
  read_in_full: 2,
  docs_ok: 100,
  scanner_version: "0.1.0",
  scanned_at: "2026-08-01T10:00:00Z",
  docs_changed: true,
  /* A reason is what makes the rescan button render at all: without one the
     page shows "up to date" and there would be nothing for a role to hide. */
  rescan_reason: "drift",
  overall_breakdown: { ok: 2 },
  unread_breakdown: {},
  unread_documents: 0,
  rows_unrecognized: 0,
  section_rollup: {},
  error: null,
  error_at: null,
  active_snapshot: {
    id: 3,
    commit_hash: "a".repeat(40),
    scanner_version: "0.1.0",
    last_scanned_at: "2026-08-01T10:00:00Z",
    documents_total: 2,
    docs_ok: 100,
    parser_ok: 100,
    completeness: 1,
    created_at: "2026-08-01T10:00:00Z",
  },
  latest_snapshot: { id: 3, commit_hash: "a".repeat(40) },
  head_commit: "b".repeat(40),
  interruption: null,
  top_issues: [],
  non_endpoint_documents: 0,
} as unknown as ServiceDetail;

function servicePage() {
  return renderPage(<ServicePage />, {
    // The repo name holds a slash, so the app links to it encoded and the route
    // matches one segment - exactly as RegistryPage navigates.
    path: `/scan/services/${encodeURIComponent(NAME)}`,
    route: "/scan/services/:name",
    seed: [[keys.service(NAME), SERVICE]],
  });
}

beforeEach(() => stubEmptyApi());
afterEach(() => vi.unstubAllGlobals());

describe("a viewer sees a read-only panel", () => {
  beforeEach(() => {
    session.token = tokenWithRoles("viewer");
  });

  it("is offered no rescan", () => {
    servicePage();

    expect(screen.queryByRole("button", { name: /rescan/i })).toBeNull();
  });

  it("is offered no way to exclude the service", () => {
    servicePage();

    expect(screen.queryByRole("button", { name: /exclude/i })).toBeNull();
  });

  it("can still read the snapshot it is being served, but not switch it", () => {
    servicePage();

    // Present and disabled rather than gone: which snapshot is active is
    // information, and hiding it would answer a question nobody asked.
    expect(screen.getByRole("button", { name: /Snapshot 3/ })).toBeDisabled();
  });

  it("still sees the panel's data", () => {
    servicePage();

    expect(screen.getByText("ecs")).toBeInTheDocument();
    expect(screen.getByText(/Clean documents/i)).toBeInTheDocument();
  });
});

describe("a worker sees the controls", () => {
  beforeEach(() => {
    session.token = tokenWithRoles("worker");
  });

  it("is offered the rescan the viewer was not", () => {
    servicePage();

    expect(screen.getByRole("button", { name: /rescan/i })).toBeInTheDocument();
  });

  it("is offered the exclude control", () => {
    servicePage();

    expect(screen.getByRole("button", { name: /exclude/i })).toBeInTheDocument();
  });

  it("can switch snapshots", () => {
    servicePage();

    expect(screen.getByRole("button", { name: /Snapshot 3/ })).toBeEnabled();
  });

});

describe("a session with no panel role at all", () => {
  it("is treated as a viewer, not as a worker", () => {
    // The backend answers 401 to this token; the UI must not meanwhile offer
    // controls on the assumption that a signed-in user can act.
    session.token = tokenWithRoles();

    servicePage();

    expect(screen.queryByRole("button", { name: /rescan/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /exclude/i })).toBeNull();
  });
});

describe("the header says which session this is", () => {
  it("labels a viewer read-only, so the missing controls are explained once", () => {
    session.token = tokenWithRoles("viewer");

    renderPage(<Header />);

    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.getByText("ada@otc.test")).toBeInTheDocument();
  });

  it("labels a worker nothing - the controls speak for themselves", () => {
    session.token = tokenWithRoles("worker");

    renderPage(<Header />);

    expect(screen.queryByText(/read-only/i)).toBeNull();
  });

  it("offers a way out of the session", () => {
    session.token = tokenWithRoles("worker");

    renderPage(<Header />);

    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });
});
