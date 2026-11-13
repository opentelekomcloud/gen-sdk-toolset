import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, within } from "@testing-library/react";
import { alertNamed, backend, FAILED, later, pollAgain, refresh, renderPage } from "../../../test/render";
import { serviceDetail, snapshot } from "../../../test/fixtures";
import { tokenWithRoles } from "../../../test/token";
import { keys } from "../api/queries";
import { createQueryClient } from "../../../shared/api/queryClient";
import { Header } from "../../../components/Header";
import { AttentionBand } from "../components/AttentionBand";
import { RegistryPage } from "./RegistryPage";
import { ServicePage } from "./ServicePage";

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
const API = {
  summary: "/api/scan/summary",
  attention: "/api/scan/attention",
  services: "/api/scan/services",
  excluded: "/api/scan/excluded",
  ineligible: "/api/scan/ineligible",
  service: `/api/scan/services/${encodeURIComponent(NAME)}`,
  documents: `/api/scan/services/${encodeURIComponent(NAME)}/documents`,
  snapshots: `/api/scan/services/${encodeURIComponent(NAME)}/snapshots`,
  document: `/api/scan/services/${encodeURIComponent(NAME)}/documents/7`,
};

const SUMMARY = { scanner_version: "0.2.0", services_total: 3, failed_services: 1, scans_running: 2 };
const SCAN_RULES = [{ code: "drift", panel: "scan", label: "docs changed since last scan", count: 4 }];
const ROW = {
  name: NAME,
  label: "ecs",
  scan_status: "scanned",
  documents: 2,
  read_in_full: 2,
  docs_ok: 100,
  unread_documents: 0,
  /* older than the summary's: a row the list marks as outdated, while it knows */
  scanner_version: "0.1.0",
  overall_breakdown: { ok: 2 },
  unread_breakdown: {},
  section_rollup: {},
  rescan_reason: "version",
  job_id: null,
  initiated_by: null,
  error: null,
};
const SERVICES = { items: [ROW], counts: { all: 1, scanned: 1 } };
const EXCLUDED = [
  { name: "opentelekomcloud-docs/old", reason: "retired", excluded_by: "ada", excluded_at: "2026-08-01" },
];
const INELIGIBLE = [{ repo: "opentelekomcloud-docs/wiki", name: "wiki", branch: "main", checked_at: null }];
const SERVICE = serviceDetail({ name: NAME });
const DOC = {
  id: 7,
  path: "api-ref/source/list_servers.rst",
  title: "Listing servers",
  method: "GET",
  uri: "/v1/servers",
  overall_status: "ok",
  issues: [],
};
const DOCUMENTS = {
  items: [DOC],
  total: 1,
  page: 1,
  page_size: 20,
  doc_counts: { all: 1, ok: 1 },
  version_counts: { v1: 1 },
};
const SNAPSHOTS = { items: [snapshot()] };

/** The Registry as it is on screen: the Header and the band above the page. */
function registry() {
  return renderPage(
    <>
      <Header />
      <AttentionBand />
      <RegistryPage />
    </>,
    {
      path: "/scan",
      route: "/scan",
      seed: [
        [keys.attention, SCAN_RULES],
        [keys.services({ status: "all", q: "", sort: "quality", rule: undefined }), SERVICES],
        [keys.excluded, EXCLUDED],
        [keys.ineligible, INELIGIBLE],
      ],
    },
  );
}

function servicePage() {
  return renderPage(<ServicePage />, {
    path: `/scan/services/${encodeURIComponent(NAME)}`,
    route: "/scan/services/:name",
    seed: [
      [keys.service(NAME), SERVICE],
      [keys.documents(NAME, { status: "all", q: "", page: 1 }), DOCUMENTS],
    ],
  });
}

beforeEach(() => {
  session.token = tokenWithRoles("worker");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the Header when the summary fails to refresh", () => {
  it("shows the failure and a Retry in place of the counters", async () => {
    const answers: Record<string, unknown> = { [API.summary]: SUMMARY };
    backend(answers);
    const { client } = registry();
    await refresh(client, keys.summary);
    expect(await screen.findByText("scans running: 2")).toBeInTheDocument();

    answers[API.summary] = FAILED;
    await refresh(client, keys.summary);

    const failure = await alertNamed("Counters failed to load");
    expect(within(failure).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("scans running: 2")).toBeNull();
    expect(screen.queryByText("scanner v0.2.0")).toBeNull();
  });

  it("loads the counters again on Retry, without reloading the page", async () => {
    const answers: Record<string, unknown> = { [API.summary]: FAILED };
    const server = backend(answers);
    const { client } = registry();
    await refresh(client, keys.summary);
    await alertNamed("Counters failed to load");

    answers[API.summary] = { ...SUMMARY, scans_running: 1 };
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("scans running: 1")).toBeInTheDocument();
    expect(screen.queryByText("Counters failed to load")).toBeNull();
    expect(server.calls(API.summary)).toBe(2);
  });

  it("says it is loading while the Retry runs, and offers no second Retry", async () => {
    const answers: Record<string, unknown> = { [API.summary]: FAILED };
    backend(answers);
    const { client } = registry();
    await refresh(client, keys.summary);
    await alertNamed("Counters failed to load");

    const summary = later();
    answers[API.summary] = summary.arrived;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Loading counters…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    summary.send(SUMMARY);
    expect(await screen.findByText("scans running: 2")).toBeInTheDocument();
  });
});

describe("a failed block while the periodic refresh asks again", () => {
  it("keeps the failure and its Retry on screen, and shows the data once an answer comes", async () => {
    const answers: Record<string, unknown> = { [API.services]: FAILED, [API.summary]: FAILED };
    backend(answers);
    const { client } = registry();
    await refresh(client, keys.services());
    await refresh(client, keys.summary);
    const listFailure = await alertNamed("Failed to load the service list");
    const counterFailure = await alertNamed("Counters failed to load");

    const services = later();
    const summary = later();
    answers[API.services] = services.arrived;
    answers[API.summary] = summary.arrived;
    // the periodic refresh, not a click: nothing on screen may change for it
    await pollAgain(client, keys.services(), keys.summary);
    expect(client.isFetching()).toBe(2);

    expect(screen.getByText("Failed to load the service list").closest("[role=alert]")).toBe(listFailure);
    expect(within(listFailure).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByText("Counters failed to load").closest("[role=alert]")).toBe(counterFailure);
    expect(within(counterFailure).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("Loading services…")).toBeNull();
    expect(screen.queryByText("Loading counters…")).toBeNull();

    services.send(SERVICES);
    summary.send(SUMMARY);
    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(await screen.findByText("scans running: 2")).toBeInTheDocument();
  });
});

describe("a block whose first load failed, while it is asked again", () => {
  it("keeps the Header's failure, the sections and the documents in place", async () => {
    const answers: Record<string, unknown> = {
      [API.summary]: FAILED,
      [API.excluded]: FAILED,
      [API.documents]: FAILED,
    };
    backend(answers);
    const registryPage = renderPage(
      <>
        <Header />
        <RegistryPage />
      </>,
      { path: "/scan", route: "/scan", seed: [[keys.services({ status: "all", q: "", sort: "quality", rule: undefined }), SERVICES]] },
    );
    // render.tsx seeds a summary; reset it so the Header's load is a first one
    await act(() => registryPage.client.resetQueries({ queryKey: keys.summary }));
    const counters = await alertNamed("Counters failed to load");
    const excluded = await alertNamed("Failed to load the excluded services");

    answers[API.summary] = later().arrived;
    answers[API.excluded] = later().arrived;
    await pollAgain(registryPage.client, keys.summary, keys.excluded);

    expect(screen.getByText("Counters failed to load").closest("[role=alert]")).toBe(counters);
    expect(screen.getByText("Failed to load the excluded services").closest("[role=alert]")).toBe(excluded);
    registryPage.unmount();

    const { client } = renderPage(<ServicePage />, {
      path: `/scan/services/${encodeURIComponent(NAME)}`,
      route: "/scan/services/:name",
      seed: [[keys.service(NAME), SERVICE]],
    });
    const documents = await alertNamed("Failed to load documents");
    answers[API.documents] = later().arrived;
    await pollAgain(client, keys.documents(NAME));

    expect(screen.getByText("Failed to load documents").closest("[role=alert]")).toBe(documents);
    expect(screen.getByPlaceholderText("Filter docs…")).toBeInTheDocument();
  });

  it("keeps an open snapshot list's failure", async () => {
    const answers: Record<string, unknown> = { [API.snapshots]: FAILED };
    backend(answers);
    const { client } = servicePage();
    fireEvent.click(await screen.findByRole("button", { name: /Snapshot 3/ }));
    const failure = await alertNamed("Failed to load snapshots");

    answers[API.snapshots] = later().arrived;
    await pollAgain(client, keys.snapshots(NAME));

    expect(screen.getByText("Failed to load snapshots").closest("[role=alert]")).toBe(failure);
  });

});

describe("the documents after a failed refresh", () => {
  it("do not come back from the failed answer while another filter loads", async () => {
    const answers: Record<string, unknown> = { [API.documents]: FAILED };
    backend(answers);
    const { client } = servicePage();
    expect(await screen.findByText("Listing servers")).toBeInTheDocument();
    await refresh(client, keys.documents(NAME));
    await alertNamed("Failed to load documents");

    const next = later();
    answers[API.documents] = next.arrived;
    const search = screen.getByPlaceholderText("Filter docs…");
    search.focus();
    fireEvent.change(search, { target: { value: "list" } });

    // the new search is on its way: nothing of the answer that failed is shown
    // meanwhile, and the field being typed in stays where it is (ADR-0060)
    await act(() => new Promise((resolve) => setTimeout(resolve, 400)));
    expect(screen.queryByText("Listing servers")).toBeNull();
    expect(screen.getByText("Loading documents…")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Filter docs…")).toBe(search);
    expect(document.activeElement).toBe(search);
    next.send(DOCUMENTS);
    expect(await screen.findByText("Listing servers")).toBeInTheDocument();
  });

  /* The block leaves its failure for the new search, so the Retry's "loading"
     goes with it: it never stands for a query the block no longer shows. */
  it("drop a Retry still running for the search before, once the new one fails", async () => {
    const stuck = later();
    let calls = 0;
    const answers: Record<string, unknown> = { [API.documents]: FAILED };
    backend(answers);
    const { client } = servicePage();
    await screen.findByText("Listing servers");
    await refresh(client, keys.documents(NAME));
    await alertNamed("Failed to load documents");

    // the Retry never gets an answer; the next search does, and fails
    answers[API.documents] = () => (calls++ === 0 ? stuck.arrived : FAILED);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Loading documents…")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Filter docs…"), { target: { value: "list" } });

    const failure = await alertNamed("Failed to load documents");
    expect(within(failure).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("Loading documents…")).toBeNull();
  });
});

describe("a Retry while the periodic refresh is already asking", () => {
  it("joins that request instead of sending another one", async () => {
    const answers: Record<string, unknown> = { [API.services]: FAILED };
    const server = backend(answers);
    const { client } = registry();
    await refresh(client, keys.services());
    const failure = await alertNamed("Failed to load the service list");
    const services = later();
    answers[API.services] = services.arrived;
    await pollAgain(client, keys.services());
    const asked = server.calls(API.services);

    fireEvent.click(within(failure).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Loading services…")).toBeInTheDocument();
    expect(server.calls(API.services)).toBe(asked);
    services.send(SERVICES);
    expect(await screen.findByText("ecs")).toBeInTheDocument();
  });
});

describe("the Registry when its service list fails to refresh", () => {
  it("shows the failure and a Retry instead of the rows it had", async () => {
    backend({ [API.services]: FAILED, [API.summary]: SUMMARY });
    const { client } = registry();
    expect(await screen.findByText("ecs")).toBeInTheDocument();

    await refresh(client, keys.services());

    const failure = await alertNamed("Failed to load the service list");
    expect(within(failure).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("ecs")).toBeNull();
    expect(screen.queryByText("Service")).toBeNull();
  });

  it("leaves the blocks that did refresh in place", async () => {
    backend({ [API.services]: FAILED, [API.summary]: SUMMARY });
    const { client } = registry();
    await refresh(client, keys.summary);

    await refresh(client, keys.services());
    await alertNamed("Failed to load the service list");

    expect(screen.getByText("scans running: 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /docs changed since last scan/ })).toBeInTheDocument();
    expect(screen.getByText("Excluded services")).toBeInTheDocument();
    expect(screen.getByText("No API reference")).toBeInTheDocument();
    // the filters stay usable, but count nothing they no longer have an answer for
    expect(screen.getByRole("button", { name: "All" })).toHaveTextContent(/^All$/);
  });

  it("shows the rows again once Retry gets an answer", async () => {
    const answers: Record<string, unknown> = { [API.services]: FAILED };
    const server = backend(answers);
    const { client } = registry();
    await refresh(client, keys.services());
    await alertNamed("Failed to load the service list");

    answers[API.services] = SERVICES;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(screen.queryByText("Failed to load the service list")).toBeNull();
    expect(server.calls(API.services)).toBe(2);
  });

  it("does not show summary numbers from before while the summary is failing", async () => {
    const answers: Record<string, unknown> = { [API.summary]: SUMMARY };
    backend(answers);
    const { client } = registry();
    await refresh(client, keys.summary);
    expect(await screen.findByText(/1 repos failed and hold no data/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rescan · v0.2.0" })).toBeInTheDocument();

    answers[API.summary] = FAILED;
    await refresh(client, keys.summary);
    await alertNamed("Counters failed to load");

    expect(screen.queryByText(/1 repos failed and hold no data/)).toBeNull();
    expect(screen.getByRole("button", { name: "Rescan · new scanner" })).toBeInTheDocument();
    // no version to compare against, so no row is marked as scanned by an old one
    expect(screen.queryByText(/· v0\.1\.0/)).toBeNull();
    expect(screen.getByText("ecs")).toBeInTheDocument();
  });
});

describe.each([
  ["excluded", "Excluded services", "Failed to load the excluded services", keys.excluded, EXCLUDED, "opentelekomcloud-docs/old"],
  [
    "ineligible",
    "No API reference",
    "Failed to load the services without an API reference",
    keys.ineligible,
    INELIGIBLE,
    "opentelekomcloud-docs/wiki",
  ],
] as const)("the %s section when it fails to refresh", (path, title, failed, key, answer, row) => {
  it("keeps its title and shows the failure, folded or not, in place of its count", async () => {
    const answers: Record<string, unknown> = { [API[path]]: FAILED };
    backend(answers);
    const { client } = registry();
    expect(screen.getByRole("button", { name: `${title} 1` })).toBeInTheDocument();

    await refresh(client, key);

    await alertNamed(failed);
    // the title stays, the count it had is gone with the rest of the answer
    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: new RegExp(title) })).toBeNull();
    expect(screen.getByText("ecs")).toBeInTheDocument();
  });

  it("shows the failure in place of the rows of an open section", async () => {
    backend({ [API[path]]: FAILED });
    const { client } = registry();
    fireEvent.click(screen.getByRole("button", { name: `${title} 1` }));
    expect(screen.getByText(row)).toBeInTheDocument();

    await refresh(client, key);

    await alertNamed(failed);
    expect(screen.queryByText(row)).toBeNull();
  });

  it("shows its count again once Retry gets an answer", async () => {
    const answers: Record<string, unknown> = { [API[path]]: FAILED };
    backend(answers);
    const { client } = registry();
    await refresh(client, key);
    const failure = await alertNamed(failed);

    answers[API[path]] = answer;
    fireEvent.click(within(failure).getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: `${title} ${answer.length}` })).toBeInTheDocument();
    expect(screen.queryByText(failed)).toBeNull();
  });
});

describe("the service page when one of its blocks fails to refresh", () => {
  it("replaces the documents, keeps the search and the rest of the page", async () => {
    backend({ [API.documents]: FAILED });
    const { client } = servicePage();
    expect(await screen.findByText("Listing servers")).toBeInTheDocument();

    await refresh(client, keys.documents(NAME));

    const failure = await alertNamed("Failed to load documents");
    expect(within(failure).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("Listing servers")).toBeNull();
    expect(screen.getByPlaceholderText("Filter docs…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "ecs" })).toBeInTheDocument();
  });

  it("keeps a status filter whose request fails, so it can be taken off", async () => {
    backend({ [API.documents]: FAILED });
    servicePage();

    fireEvent.click(await screen.findByRole("button", { name: "ok 1" }));

    await alertNamed("Failed to load documents");
    expect(screen.getByRole("button", { name: "ok" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "all" }));
    expect(await screen.findByText("Listing servers")).toBeInTheDocument();
  });

  it("keeps a version filter whose request fails, so it can be taken off", async () => {
    backend({ [API.documents]: FAILED });
    renderPage(<ServicePage />, {
      path: `/scan/services/${encodeURIComponent(NAME)}`,
      route: "/scan/services/:name",
      seed: [
        [keys.service(NAME), SERVICE],
        [keys.documents(NAME, { status: "all", q: "", page: 1 }), { ...DOCUMENTS, version_counts: { v1: 1, v2: 1 } }],
      ],
    });

    fireEvent.click(await screen.findByRole("button", { name: "v2 1" }));

    await alertNamed("Failed to load documents");
    fireEvent.click(screen.getByRole("button", { name: "v2" }));
    expect(await screen.findByText("Listing servers")).toBeInTheDocument();
  });

  it("shows the documents again once Retry gets an answer", async () => {
    const answers: Record<string, unknown> = { [API.documents]: FAILED };
    backend(answers);
    const { client } = servicePage();
    await refresh(client, keys.documents(NAME));
    await alertNamed("Failed to load documents");

    answers[API.documents] = DOCUMENTS;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Listing servers")).toBeInTheDocument();
  });

  it("replaces an open snapshot list, and brings it back on Retry", async () => {
    const answers: Record<string, unknown> = { [API.snapshots]: SNAPSHOTS };
    backend(answers);
    const { client } = servicePage();
    fireEvent.click(await screen.findByRole("button", { name: /Snapshot 3/ }));
    expect(await screen.findByText("latest")).toBeInTheDocument();

    answers[API.snapshots] = FAILED;
    await refresh(client, keys.snapshots(NAME));

    const failure = await alertNamed("Failed to load snapshots");
    expect(screen.queryByText("latest")).toBeNull();

    answers[API.snapshots] = SNAPSHOTS;
    fireEvent.click(within(failure).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("latest")).toBeInTheDocument();
  });

  it("says an open document's details are loading while their Retry runs", async () => {
    const answers: Record<string, unknown> = { [API.document]: FAILED };
    backend(answers);
    servicePage();
    fireEvent.click(await screen.findByText("Listing servers"));
    await alertNamed("Failed to load document detail");

    const detail = later();
    answers[API.document] = detail.arrived;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    // the Retry's own "loading", then the row's: one text, two elements in turn
    await screen.findByText("Loading document detail…");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    detail.send({ ...DOC, sections: [], source_url: "https://example.test", api_version: "v1", failure_reason: null });
    expect(await screen.findByText("v1")).toBeInTheDocument();
  });
});

describe("with the panel's own query client", () => {
  /* retry: 1 - a block shows the failure only once the built-in retry failed
     too, so a single dropped request never flashes an error */
  const flush = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

  it("shows nothing wrong when the built-in retry succeeds", async () => {
    vi.useFakeTimers();
    let failures = 1;
    backend({ [API.summary]: () => (failures-- > 0 ? FAILED : SUMMARY) });
    const client = createQueryClient();
    renderPage(<Header />, { client });
    void client.invalidateQueries({ queryKey: keys.summary });

    await flush(5_000);

    expect(screen.queryByText("Counters failed to load")).toBeNull();
    expect(screen.getByText("scans running: 2")).toBeInTheDocument();
  });

  it("shows the failure once the built-in retry failed as well", async () => {
    vi.useFakeTimers();
    const server = backend({ [API.summary]: FAILED });
    const client = createQueryClient();
    renderPage(<Header />, { client });
    void client.invalidateQueries({ queryKey: keys.summary });

    await flush(500);
    expect(screen.queryByText("Counters failed to load")).toBeNull();

    await flush(5_000);
    expect(screen.getByText("Counters failed to load")).toBeInTheDocument();
    expect(server.calls(API.summary)).toBe(2);
  });
});
