import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router";
import { renderPage } from "../../../test/render";
import { keys } from "../../scan/api/queries";
import type { GenService, GenTarget } from "../data/types";
import { GenerationListPage } from "./GenerationListPage";

/** Where the page navigated to. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

/** Route "*" keeps the page mounted after it navigates, so the address can be read. */
function listPage(path = "/generation", seed?: [readonly unknown[], unknown][]) {
  return renderPage(
    <>
      <GenerationListPage />
      <Location />
    </>,
    { path, route: "*", seed },
  );
}

const location = () => screen.getByTestId("location").textContent;

/* Tests drive the hidden state switched on, so it does not rot; the last block checks it switched off. */
const flags = vi.hoisted(() => ({ showGenState: true }));

vi.mock("../flags", () => ({
  get SHOW_GEN_STATE() {
    return flags.showGenState;
  },
}));

afterEach(() => {
  flags.showGenState = true;
});

describe("the Generation list on the in-memory mock", () => {
  it("lists the services scanned in full or in part, with a column per target", async () => {
    listPage();

    expect(await screen.findByText("billing-api")).toBeInTheDocument();
    for (const name of ["customer-core", "device-mgmt", "notifications-hub", "tariff-catalog"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    // failed, still scanning, never scanned: not in Generation
    for (const name of ["sms-gateway", "legacy-soap-bridge", "payments-gw", "roaming-info"]) {
      expect(screen.queryByText(name)).toBeNull();
    }
    expect(screen.getByText("Python SDK")).toBeInTheDocument();
    expect(screen.getByText("Ansible modules · TBD")).toBeInTheDocument();
  });

  it("shows each service's state and merged share per target", async () => {
    listPage();

    expect(await screen.findByTitle("Python SDK · Waiting for review · 0 of 4 resources merged")).toHaveTextContent(
      "Waiting for review",
    );
    expect(screen.getByTitle("Python SDK · Failed · 1 of 3 resources merged")).toBeInTheDocument();
    expect(screen.getByTitle("Python SDK · Partial · 1 of 2 resources merged")).toBeInTheDocument();
    // Ansible is not connected and builds on Python
    expect(
      screen.getByTitle("Ansible modules · not connected · 0 of 4 resources merged · builds on Python SDK"),
    ).toHaveTextContent("not connected");
    expect(screen.getAllByText("1/3")).toHaveLength(1);
  });

  it("counts the services behind every chip", async () => {
    listPage();

    await screen.findByText("billing-api");
    for (const name of [
      "All 5",
      "Not generated 2",
      "In progress 0",
      "Failed 1",
      "Waiting for review 1",
      "Partial 1",
    ]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
  });
});

describe("the filter lives in the address", () => {
  it("opens narrowed to the services waiting for review", async () => {
    listPage("/generation?filter=review");

    expect(await screen.findByText("billing-api")).toBeInTheDocument();
    expect(screen.queryByText("customer-core")).toBeNull();
    expect(screen.queryByText("notifications-hub")).toBeNull();
  });

  it("opens narrowed to the services with nothing generated", async () => {
    listPage("/generation?filter=not_generated");

    expect(await screen.findByText("device-mgmt")).toBeInTheDocument();
    expect(screen.getByText("tariff-catalog")).toBeInTheDocument();
    for (const name of ["billing-api", "customer-core", "notifications-hub"]) {
      expect(screen.queryByText(name)).toBeNull();
    }
    expect(screen.getByRole("button", { name: "Not generated 2" })).toHaveClass("bg-brand");
    // device-mgmt has resources, none of them generated; tariff-catalog has none, so no merged share to show
    expect(screen.getByTitle("Python SDK · Not generated · 0 of 6 resources merged")).toBeInTheDocument();
    expect(screen.getByTitle("Python SDK · Not generated")).toBeInTheDocument();
    expect(screen.getAllByText(/^\d+\/\d+$/).map((e) => e.textContent)).toEqual(["0/6", "0/6"]);
  });

  it("opens narrowed to the services merged in part", async () => {
    listPage("/generation?filter=partial");

    expect(await screen.findByTitle("Python SDK · Partial · 1 of 2 resources merged")).toBeInTheDocument();
    expect(screen.getByText("notifications-hub")).toBeInTheDocument();
    expect(screen.getByText("1/2")).toBeInTheDocument();
    for (const name of ["billing-api", "customer-core", "device-mgmt", "tariff-catalog"]) {
      expect(screen.queryByText(name)).toBeNull();
    }
  });

  it("follows a chip click, and drops the filter again on All", async () => {
    listPage();

    fireEvent.click(await screen.findByRole("button", { name: "Failed 1" }));

    expect(location()).toBe("/generation?filter=failed");
    expect(screen.getByText("customer-core")).toBeInTheDocument();
    expect(screen.queryByText("billing-api")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "All 5" }));

    expect(location()).toBe("/generation");
    expect(screen.getByText("billing-api")).toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    listPage("/generation?filter=in_progress");

    expect(await screen.findByText("No services match the current filter.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All 5" })).toBeInTheDocument();
    expect(screen.queryByText("billing-api")).toBeNull();
  });
});

describe("search", () => {
  it("narrows the rows and the chip counts together", async () => {
    listPage();

    fireEvent.change(await screen.findByPlaceholderText("Filter services…"), { target: { value: "core" } });

    await waitFor(() => expect(location()).toBe("/generation?q=core"));
    expect(screen.getByText("customer-core")).toBeInTheDocument();
    expect(screen.queryByText("billing-api")).toBeNull();
    expect(screen.getByRole("button", { name: "All 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Failed 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for review 0" })).toBeInTheDocument();
  });
});

describe("the way into a service card", () => {
  it("opens on the default target from the row", async () => {
    listPage();

    fireEvent.click(await screen.findByText("billing-api"));

    expect(location()).toBe("/generation/billing-api");
  });

  it("opens on the clicked target from its cell", async () => {
    listPage();

    fireEvent.click(await screen.findByTitle(/^Ansible modules · not connected · 0 of 4/));

    expect(location()).toBe("/generation/billing-api?target=ansible");
  });
});

describe("states the mock does not hold today", () => {
  const TARGETS: GenTarget[] = [
    { id: "python", label: "Python SDK", live: true, base: null, repo: "opentelekomcloud/python-t-cloud" },
    { id: "ansible", label: "Ansible modules", live: false, base: "python", repo: "opentelekomcloud/ansible-collection-cloud" },
  ];
  const service = (name: string, state: GenService["targets"][string]["state"], merged: number): GenService => ({
    name,
    targets: {
      python: { state, merged, total: 2 },
      ansible: { state: "not_generated", merged: 0, total: 2 },
    },
  });
  const SEED: [readonly unknown[], unknown][] = [
    [keys.genTargets, TARGETS],
    [
      keys.genServices,
      [service("running-svc", "in_progress", 0), service("merged-svc", "done", 2)],
    ],
  ];

  it("shows a running generation as in progress", async () => {
    listPage("/generation", SEED);

    expect(await screen.findByTitle("Python SDK · In progress · 0 of 2 resources merged")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "In progress 1" })).toBeInTheDocument();
  });

  it("opens narrowed to the running generations, the pill spinning", async () => {
    listPage("/generation?filter=in_progress", SEED);

    const pill = await screen.findByTitle("Python SDK · In progress · 0 of 2 resources merged");
    expect(pill.querySelector(".animate-spin")).not.toBeNull();
    expect(screen.getByText("running-svc")).toBeInTheDocument();
    expect(screen.queryByText("No services match the current filter.")).toBeNull();
  });

  it("leaves out a service merged in full, from the rows and the counts", async () => {
    listPage("/generation", SEED);

    expect(await screen.findByText("running-svc")).toBeInTheDocument();
    expect(screen.queryByText("merged-svc")).toBeNull();
    expect(screen.getByRole("button", { name: "All 1" })).toBeInTheDocument();
  });
});

describe("with the per-target state switched off: the list the backend serves", () => {
  const ECS = { name: "opentelekomcloud-docs/ecs", label: "ecs" };
  const VPC = { name: "opentelekomcloud-docs/vpc", label: "vpc" };
  const BACKEND: [readonly unknown[], unknown][] = [[keys.genList({ q: "" }), [ECS, VPC]]];

  beforeEach(() => {
    flags.showGenState = false;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists every service the backend returned, by label only, under a single service column", async () => {
    listPage("/generation", BACKEND);

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(screen.getByText("vpc")).toBeInTheDocument();
    expect(screen.getByText("Service")).toBeInTheDocument();
    expect(screen.queryByText("opentelekomcloud-docs/ecs")).toBeNull();
    expect(screen.queryByText("Python SDK")).toBeNull();
    expect(screen.queryByText("billing-api")).toBeNull();
  });

  it("asks the backend for the list", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([ECS]), { headers: { "Content-Type": "application/json" } }));

    listPage();

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(fetch.mock.calls[0][0]).toBe("/api/generation/services");
  });

  it("shows nothing about generation in a row", async () => {
    listPage("/generation", BACKEND);

    await screen.findByText("ecs");
    for (const state of ["Not generated", "In progress", "Failed", "Waiting for review", "Partial", "not connected"]) {
      expect(screen.queryByText(state)).toBeNull();
    }
    expect(screen.queryByTitle(/resources merged/)).toBeNull();
    expect(screen.queryByText(/^\d+\/\d+$/)).toBeNull();
  });

  it("has no state chips", async () => {
    listPage("/generation", BACKEND);

    await screen.findByText("ecs");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("does not apply a filter from the address", async () => {
    listPage("/generation?filter=review", BACKEND);

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(screen.getByText("vpc")).toBeInTheDocument();
  });

  it("says so when the backend returns no services", async () => {
    listPage("/generation", [[keys.genList({ q: "" }), []]]);

    expect(await screen.findByText("No services match the current filter.")).toBeInTheDocument();
  });

  it("searches through the backend, the text kept in the address", async () => {
    listPage("/generation", [...BACKEND, [keys.genList({ q: "vp" }), [VPC]]]);

    fireEvent.change(await screen.findByPlaceholderText("Filter services…"), { target: { value: "vp" } });

    await waitFor(() => expect(location()).toBe("/generation?q=vp"));
    expect(await screen.findByText("vpc")).toBeInTheDocument();
    expect(screen.queryByText("ecs")).toBeNull();
  });

  it("opens with the search the address holds", async () => {
    listPage("/generation?q=vp", [[keys.genList({ q: "vp" }), [VPC]]]);

    expect(await screen.findByText("vpc")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Filter services…")).toHaveValue("vp");
  });

  it("opens a service card from the row", async () => {
    listPage("/generation", BACKEND);

    fireEvent.click(await screen.findByText("ecs"));

    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs");
  });
});

describe("a scan that ends while the list is open", () => {
  const ECS = { name: "opentelekomcloud-docs/ecs", label: "ecs" };
  const VPC = { name: "opentelekomcloud-docs/vpc", label: "vpc" };
  const DNS = { name: "opentelekomcloud-docs/dns", label: "dns" };
  const scanningItem = (service: { name: string }, job_id: number) => ({ name: service.name, scan_status: "scanning", job_id });
  /** The header's summary as it reads while scans are running. */
  const SCANNING: [readonly unknown[], unknown][] = [
    [keys.summary, { scanner_version: "0.1.0", services_total: 3, scans_running: 1 }],
  ];

  interface Backend {
    /** One answer per request to the scanning services, the last repeated; a number is an error status. */
    scanning: (unknown[] | number)[];
    /** Per job, its status on each poll, the last repeated. */
    jobs: Record<number, string[]>;
    /** The Generation list on each request, the last repeated. */
    lists: unknown[][];
    /** `scans_running` on each summary refetch, the last repeated. */
    running?: number[];
  }

  function stubBackend(backend: Backend) {
    const seen: Record<string, number> = {};
    const nth = <T,>(answers: T[], key: string) => {
      seen[key] = (seen[key] ?? 0) + 1;
      return answers[Math.min(seen[key], answers.length) - 1];
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://panel.test");
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
      if (url.pathname === "/api/scan/services") {
        const answer = nth(backend.scanning, "scanning");
        return typeof answer === "number"
          ? json({ error: { code: "internal_error", message: "boom" } }, answer)
          : json({ items: answer, counts: {} });
      }
      if (url.pathname === "/api/scan/summary") {
        const scans_running = nth(backend.running ?? [0], "summary");
        return json({ scanner_version: "0.1.0", services_total: 3, scans_running });
      }
      const job = /^\/api\/jobs\/(\d+)$/.exec(url.pathname);
      if (job) {
        const id = Number(job[1]);
        return json({ id, kind: "scan", status: nth(backend.jobs[id], `job ${id}`) });
      }
      if (url.pathname === "/api/generation/services") return json(nth(backend.lists, "list"));
      return json([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const calls = (path: string) => fetchMock.mock.calls.filter(([input]) => String(input).startsWith(path)).length;
    return { calls };
  }

  /** A job poll comes every 1.5s, so a second terminal edge takes longer than findBy's default. */
  const SLOW = { timeout: 5000 };

  beforeEach(() => {
    flags.showGenState = false;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks the backend for the list again, and shows what it answers", async () => {
    const { calls } = stubBackend({
      scanning: [[scanningItem(VPC, 7)]],
      jobs: { 7: ["done"] },
      lists: [[ECS], [ECS, VPC]],
    });

    listPage("/generation", SCANNING);

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(await screen.findByText("vpc")).toBeInTheDocument();
    expect(calls("/api/generation/services")).toBe(2);
    // the job reached its terminal state, so it is not polled again
    expect(calls("/api/jobs/7")).toBe(1);
  });

  it("leaves the list alone when the scan failed", async () => {
    const { calls } = stubBackend({
      scanning: [[scanningItem(VPC, 7)]],
      jobs: { 7: ["failed"] },
      lists: [[ECS], [ECS, VPC]],
    });

    listPage("/generation", SCANNING);

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    // the failure refreshed the scan state - the summary - and nothing more
    await waitFor(() => expect(calls("/api/scan/summary")).toBe(1));
    expect(calls("/api/jobs/7")).toBe(1);
    expect(calls("/api/generation/services")).toBe(1);
    expect(screen.queryByText("vpc")).toBeNull();
  });

  it("asks nothing about scans while none is running", async () => {
    const { calls } = stubBackend({ scanning: [[]], jobs: {}, lists: [[ECS]] });

    listPage();

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(calls("/api/scan/services")).toBe(0);
    expect(calls("/api/jobs/")).toBe(0);
  });

  it("does not replay a scan the cache remembers from an earlier visit", async () => {
    // The scanning services as a visit some minutes ago read them: job 7 has
    // long ended, and watching it again would refresh vpc's views for nothing.
    const { calls } = stubBackend({ scanning: [[]], jobs: { 7: ["done"] }, lists: [[ECS]] });

    listPage("/generation", [[keys.services({ status: "scanning" }), { items: [scanningItem(VPC, 7)], counts: {} }]]);

    expect(await screen.findByText("ecs")).toBeInTheDocument();
    expect(calls("/api/jobs/7")).toBe(0);
    expect(calls("/api/generation/services")).toBe(1);
  });

  it("asks again on a quick return, however fresh the cached answer is", async () => {
    // A visit seconds ago read job 7 as running and the cache still holds that
    // answer; it is not watched, so this visit must read its own.
    stubBackend({
      scanning: [[scanningItem(VPC, 7)]],
      jobs: { 7: ["done"] },
      lists: [[ECS], [ECS, VPC]],
    });

    listPage("/generation", [
      ...SCANNING,
      [keys.services({ status: "scanning" }), { items: [scanningItem(VPC, 7)], counts: {} }],
    ]);

    expect(await screen.findByText("vpc")).toBeInTheDocument();
  });

  it("keeps watching the scans it read when a later refresh of them fails", async () => {
    // Job 7 ends first, and the refetch that follows it fails. Job 9 was read
    // before that, so its end still refreshes the list; once no scan is left,
    // the notice goes too - there is nothing more the list could miss.
    stubBackend({
      scanning: [[scanningItem(VPC, 7), scanningItem(DNS, 9)], 500],
      jobs: { 7: ["done"], 9: ["running", "done"] },
      lists: [[ECS], [ECS, VPC], [ECS, VPC, DNS]],
      running: [1, 0],
    });

    listPage("/generation", SCANNING);

    expect(await screen.findByText(/Running scans could not be checked/)).toBeInTheDocument();
    expect(await screen.findByText("vpc")).toBeInTheDocument();
    expect(await screen.findByText("dns", {}, SLOW)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/Running scans could not be checked/)).toBeNull());
  });

  it("keeps watching a scan that ended before its watcher saw it, when the next answer leaves it out", async () => {
    // Job 7 ends and its refetch arrives after job 9 ended too: the backend no
    // longer lists 9 as scanning, but its watcher has not polled it to the end
    // yet. Dropping the watcher with the row would leave dns off the list.
    stubBackend({
      scanning: [[scanningItem(VPC, 7), scanningItem(DNS, 9)], []],
      jobs: { 7: ["done"], 9: ["running", "done"] },
      lists: [[ECS], [ECS, VPC], [ECS, VPC, DNS]],
      running: [0],
    });

    listPage("/generation", SCANNING);

    expect(await screen.findByText("vpc")).toBeInTheDocument();
    expect(await screen.findByText("dns", {}, SLOW)).toBeInTheDocument();
  });

  it("says it stopped following the scans when they cannot be read, and recovers on Retry", async () => {
    // Another scan still counts as running throughout, so the notice can only
    // go because the retried request succeeded - not because nothing is left to watch.
    stubBackend({
      scanning: [500, [scanningItem(VPC, 7)]],
      jobs: { 7: ["done"] },
      lists: [[ECS], [ECS, VPC]],
      running: [1],
    });

    listPage("/generation", SCANNING);

    expect(await screen.findByText(/Running scans could not be checked/)).toBeInTheDocument();
    // the list itself still loaded: the notice is about the watching, not the services
    expect(screen.getByText("ecs")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    // the retried answer is watched: its job's end brings vpc in, and the notice is gone
    expect(await screen.findByText("vpc")).toBeInTheDocument();
    expect(screen.queryByText(/Running scans could not be checked/)).toBeNull();
  });
});
