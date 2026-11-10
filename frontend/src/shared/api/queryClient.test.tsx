import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { MutationObserver, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { rescanMutation } from "../../features/scan/api/mutations";
import {
  keys,
  useAttention,
  useDocumentDetail,
  useService,
  useServices,
  useSnapshots,
  useSummary,
} from "../../features/scan/api/queries";
import { createQueryClient, REFETCH_INTERVAL_MS } from "./queryClient";

const NAME = "opentelekomcloud-docs/vpc";
const SUMMARY = "/api/scan/summary";
const SERVICES = "/api/scan/services";
const DOCUMENT = `/api/scan/services/${encodeURIComponent(NAME)}/documents/3`;
const SNAPSHOTS = `/api/scan/services/${encodeURIComponent(NAME)}/snapshots`;
const ATTENTION = "/api/scan/attention";
const SERVICE = `/api/scan/services/${encodeURIComponent(NAME)}`;
const RESCAN = `${SERVICE}/rescan`;
/** The longest a visible tab may take to show a change saved on the server (ADR-0077). */
const DEADLINE_MS = 15_000;

/**
 * The server as the tab sees it: each path answers with whatever `state` holds
 * for it at the moment of the request, so a test changes the server by
 * assigning to `state`. A function there is the answer itself, for a response
 * that fails or that the test lets arrive later.
 */
function serve(state: Record<string, unknown>) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const answer = state[String(input)];
    return typeof answer === "function"
      ? (answer as () => Response | Promise<Response>)()
      : new Response(JSON.stringify(answer ?? null));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls: (path: string) => fetchMock.mock.calls.filter(([input]) => String(input) === path).length };
}

/** An answer that arrives only when the test sends it. */
function later() {
  let send: (body: unknown) => void = () => {};
  const arrived = new Promise<unknown>((resolve) => {
    send = resolve;
  });
  return { answer: () => arrived.then((body) => new Response(JSON.stringify(body))), send };
}

const failing = () =>
  new Response(JSON.stringify({ error: { code: "internal", message: "down" } }), { status: 500 });

/** What a component shows of a query: proof the answer reached the screen, not only the cache. */
function Shown({ id, data }: { id: string; data: unknown }) {
  return <output data-testid={id}>{data === undefined ? "" : JSON.stringify(data)}</output>;
}
function HeaderProbe() {
  return <Shown id="summary" data={useSummary().data} />;
}
function RegistryProbe() {
  return <Shown id="services" data={useServices({}).data} />;
}
function AttentionProbe() {
  return <Shown id="attention" data={useAttention().data} />;
}
function ServiceProbe() {
  return <Shown id="service" data={useService(NAME).data} />;
}
/** What every page shows - the Header and the Attention Band - and the open page. */
function PanelProbe() {
  return (
    <>
      <HeaderProbe />
      <AttentionProbe />
      <ServiceProbe />
    </>
  );
}
function DocumentProbe() {
  return <Shown id="document" data={useDocumentDetail(NAME, 3, true).data} />;
}
/** A block that stays mounted while closed, the way DocRow and SnapshotSelector do. */
function LazyDocumentProbe({ open }: { open: boolean }) {
  return <Shown id="lazy" data={useDocumentDetail(NAME, 3, open).data} />;
}
function LazySnapshotsProbe({ open }: { open: boolean }) {
  return <Shown id="lazy" data={useSnapshots(NAME, open).data} />;
}

/** The app's own query client, so the tests hold the settings the panel runs with. */
function mount(ui: ReactNode) {
  const client = createQueryClient();
  const wrap = (node: ReactNode) => <QueryClientProvider client={client}>{node}</QueryClientProvider>;
  const rendered = render(wrap(ui));
  return { client, rerender: (node: ReactNode) => rendered.rerender(wrap(node)) };
}

/** Lets the clock run - each refetch fires and its answer lands - without waiting it out. */
const elapse = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const shown = (id: string) => screen.getByTestId(id).textContent;

let visibility: DocumentVisibilityState = "visible";
/** Hides or shows the tab, as the browser does: the state, then the event. */
const setTab = (state: DocumentVisibilityState) =>
  act(() => {
    visibility = state;
    document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
  });

beforeEach(() => {
  vi.useFakeTimers();
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  /* back to jsdom's own, always "visible" - and told, so the panel's online
     state does not stay "hidden" for whatever runs next */
  delete (document as { visibilityState?: DocumentVisibilityState }).visibilityState;
  document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
  window.dispatchEvent(new Event("online"));
});

describe("the periodic refetch", () => {
  it("shows a change saved on the server within the deadline, with no action in the tab", async () => {
    const state: Record<string, unknown> = { [SUMMARY]: { services_total: 1 } };
    serve(state);
    mount(<HeaderProbe />);
    await elapse(0);
    expect(shown("summary")).toBe('{"services_total":1}');

    state[SUMMARY] = { services_total: 2 };
    await elapse(DEADLINE_MS);

    expect(shown("summary")).toBe('{"services_total":2}');
  });

  it("covers open document details too", async () => {
    const state: Record<string, unknown> = { [DOCUMENT]: { id: 3, title: "old" } };
    serve(state);
    mount(<DocumentProbe />);
    await elapse(0);

    state[DOCUMENT] = { id: 3, title: "new" };
    await elapse(DEADLINE_MS);

    expect(shown("document")).toBe('{"id":3,"title":"new"}');
  });

  it("does not fetch a page that is not open", async () => {
    const server = serve({ [SUMMARY]: {}, [`${SERVICES}`]: { items: [] } });
    const { rerender } = mount(
      <>
        <HeaderProbe />
        <RegistryProbe />
      </>,
    );
    await elapse(0);
    rerender(<HeaderProbe />);
    const before = server.calls(SERVICES);

    await elapse(3 * REFETCH_INTERVAL_MS);

    expect(server.calls(SERVICES)).toBe(before);
    expect(server.calls(SUMMARY)).toBeGreaterThan(1);
  });

  it("loads a page opened again from the server, not from the previous visit", async () => {
    const state: Record<string, unknown> = { [SUMMARY]: {}, [SERVICES]: { total: 1 } };
    serve(state);
    const { rerender } = mount(
      <>
        <HeaderProbe />
        <RegistryProbe />
      </>,
    );
    await elapse(0);
    expect(shown("services")).toBe('{"total":1}');

    rerender(<HeaderProbe />);
    await elapse(0);
    state[SERVICES] = { total: 2 };
    rerender(
      <>
        <HeaderProbe />
        <RegistryProbe />
      </>,
    );

    expect(shown("services")).toBe("");
    await elapse(0);
    expect(shown("services")).toBe('{"total":2}');
  });
});

describe("a block opened again while its component stays mounted", () => {
  it.each([
    ["document details", DOCUMENT, LazyDocumentProbe],
    ["the snapshot list", SNAPSHOTS, LazySnapshotsProbe],
  ])("loads %s from the server, not from the previous opening", async (_name, path, Probe) => {
    const state: Record<string, unknown> = { [path]: { v: 1 } };
    serve(state);
    const { rerender } = mount(<Probe open />);
    await elapse(0);
    expect(shown("lazy")).toBe('{"v":1}');

    rerender(<Probe open={false} />);
    state[path] = { v: 2 };
    /* Inside the 15-second staleTime: a cache kept while closed would still
       count as fresh here and be shown without asking the server. */
    await elapse(DEADLINE_MS - 1_000);
    rerender(<Probe open />);

    expect(shown("lazy")).toBe("");
    await elapse(0);
    expect(shown("lazy")).toBe('{"v":2}');
  });
});

describe("a hidden tab", () => {
  it("sends no periodic request", async () => {
    const server = serve({ [SUMMARY]: {} });
    mount(<HeaderProbe />);
    await elapse(0);
    await setTab("hidden");

    await elapse(3 * REFETCH_INTERVAL_MS);

    expect(server.calls(SUMMARY)).toBe(1);
  });

  it("sends no request for an invalidation", async () => {
    const server = serve({ [SUMMARY]: {} });
    const { client } = mount(<HeaderProbe />);
    await elapse(0);
    await setTab("hidden");

    void client.invalidateQueries({ queryKey: keys.summary });
    await elapse(0);

    expect(server.calls(SUMMARY)).toBe(1);
  });

  it("sends no request for a query mounted while it is hidden, and loads it once shown", async () => {
    const server = serve({ [SUMMARY]: { services_total: 1 } });
    await setTab("hidden");
    mount(<HeaderProbe />);

    await elapse(3 * REFETCH_INTERVAL_MS);
    expect(server.calls(SUMMARY)).toBe(0);
    expect(shown("summary")).toBe("");

    await setTab("visible");
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(1);
    expect(shown("summary")).toBe('{"services_total":1}');
  });

  /* TanStack already holds a retry in a hidden tab; this pins the criterion,
     and that the retry goes out as the one request of the return. */
  it("sends no retry after an error, and retries once shown", async () => {
    const state: Record<string, unknown> = { [SUMMARY]: failing };
    const server = serve(state);
    mount(<HeaderProbe />);
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(1);
    await setTab("hidden");

    await elapse(3 * REFETCH_INTERVAL_MS);
    expect(server.calls(SUMMARY)).toBe(1);

    state[SUMMARY] = { services_total: 1 };
    await setTab("visible");
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(2);
    expect(shown("summary")).toBe('{"services_total":1}');
  });

  it("lets a request sent before it was hidden finish, and shows its answer", async () => {
    const state: Record<string, unknown> = { [SUMMARY]: { services_total: 1 } };
    const server = serve(state);
    mount(<HeaderProbe />);
    await elapse(0);
    const slow = later();
    state[SUMMARY] = slow.answer;
    await elapse(REFETCH_INTERVAL_MS);
    expect(server.calls(SUMMARY)).toBe(2);

    await setTab("hidden");
    slow.send({ services_total: 2 });
    /* inside staleTime, so only the return rule - not staleness - can ask again */
    await elapse(2_000);

    expect(shown("summary")).toBe('{"services_total":2}');
    expect(server.calls(SUMMARY)).toBe(2);

    // an answer that came while hidden was not seen fetched: shown, it is asked again
    state[SUMMARY] = { services_total: 3 };
    await setTab("visible");
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(3);
    expect(shown("summary")).toBe('{"services_total":3}');
  });

  it("still waits for the network while visible and offline", async () => {
    const server = serve({ [SUMMARY]: {} });
    const { client } = mount(<HeaderProbe />);
    await elapse(0);

    await act(() => window.dispatchEvent(new Event("offline")));
    void client.invalidateQueries({ queryKey: keys.summary });
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(1);

    await act(() => window.dispatchEvent(new Event("online")));
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(2);
  });
});

describe("a tab shown again", () => {
  it("fetches the Header, the Attention Band and the page at once, after a few seconds hidden", async () => {
    const state: Record<string, unknown> = {
      [SUMMARY]: { services_total: 1 },
      [ATTENTION]: [],
      [SERVICE]: { scan_status: "scanned" },
    };
    const server = serve(state);
    mount(<PanelProbe />);
    await elapse(0);
    await setTab("hidden");
    // another user's activation, exclusion or undo, and a scan finishing
    state[SUMMARY] = { services_total: 2 };
    state[ATTENTION] = [{ code: "failed" }];
    state[SERVICE] = { scan_status: "failed" };
    /* well inside the 15-second staleTime: only "always" refetches data this fresh */
    await elapse(2_000);

    await setTab("visible");
    await elapse(0);

    // one request each - the return is a single fetch, not one per trigger
    expect([SUMMARY, ATTENTION, SERVICE].map(server.calls)).toEqual([2, 2, 2]);
    expect(shown("summary")).toBe('{"services_total":2}');
    expect(shown("attention")).toBe('[{"code":"failed"}]');
    expect(shown("service")).toBe('{"scan_status":"failed"}');
  });

  it("fetches once the network is back, if it was shown while offline", async () => {
    const state: Record<string, unknown> = { [SUMMARY]: { services_total: 1 } };
    const server = serve(state);
    mount(<HeaderProbe />);
    await elapse(0);
    await setTab("hidden");
    await act(() => window.dispatchEvent(new Event("offline")));
    state[SUMMARY] = { services_total: 2 };

    await setTab("visible");
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(1);

    await act(() => window.dispatchEvent(new Event("online")));
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(2);
    expect(shown("summary")).toBe('{"services_total":2}');
  });

  it("does not refetch again on the next tick when shown just before it", async () => {
    const server = serve({ [SUMMARY]: {} });
    mount(<HeaderProbe />);
    await elapse(0);
    await setTab("hidden");
    await elapse(REFETCH_INTERVAL_MS - 100);

    await setTab("visible");
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(2);

    // the old tick was due 100 ms later; the fetch on return restarted the interval
    await elapse(REFETCH_INTERVAL_MS - 1_000);
    expect(server.calls(SUMMARY)).toBe(2);
    await elapse(1_000);
    expect(server.calls(SUMMARY)).toBe(3);
  });

  it("then refreshes on the interval like any visible tab", async () => {
    const server = serve({ [SUMMARY]: {} });
    mount(<HeaderProbe />);
    await elapse(0);
    await setTab("hidden");
    await elapse(REFETCH_INTERVAL_MS);
    await setTab("visible");
    await elapse(0);
    const back = server.calls(SUMMARY);

    await elapse(2 * REFETCH_INTERVAL_MS);

    expect(server.calls(SUMMARY)).toBe(back + 2);
  });

  it("shows a scan it started itself before it was hidden", async () => {
    const state: Record<string, unknown> = {
      [SUMMARY]: { scanning: 0 },
      [ATTENTION]: [],
      [SERVICE]: { name: NAME, scan_status: "scanned" },
    };
    const server = serve(state);
    const { client } = mount(<PanelProbe />);
    await elapse(0);
    const accepted = later();
    state[RESCAN] = accepted.answer;
    void new MutationObserver(client, rescanMutation(client, NAME, "tester")).mutate();
    await elapse(0);
    expect(server.calls(RESCAN)).toBe(1);

    await setTab("hidden");
    state[SUMMARY] = { scanning: 1 };
    accepted.send({ job_id: 7 });
    await elapse(3 * REFETCH_INTERVAL_MS);
    // the invalidations of a started scan wait too
    expect(server.calls(SUMMARY)).toBe(1);

    await setTab("visible");
    await elapse(0);
    expect(server.calls(SUMMARY)).toBe(2);
    expect(shown("summary")).toBe('{"scanning":1}');
  });
});

describe("a network coming back while the tab stayed visible", () => {
  it("refetches only data older than staleTime, as TanStack does by default", async () => {
    const server = serve({ [SUMMARY]: {} });
    mount(<HeaderProbe />);
    await elapse(0);

    await act(() => window.dispatchEvent(new Event("offline")));
    await elapse(2_000);
    await act(() => window.dispatchEvent(new Event("online")));
    await elapse(0);

    expect(server.calls(SUMMARY)).toBe(1);
  });

  it("does not count a visibility event that leaves the tab visible as a return", async () => {
    const server = serve({ [SUMMARY]: {} });
    mount(<HeaderProbe />);
    await elapse(0);
    await setTab("visible");

    await act(() => window.dispatchEvent(new Event("offline")));
    await act(() => window.dispatchEvent(new Event("online")));
    await elapse(0);

    expect(server.calls(SUMMARY)).toBe(1);
  });
});

describe("the panel's online state", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("drops the listeners of the previous client when a new one is made", () => {
    const targets = [window, document];
    const added = targets.map((target) => vi.spyOn(target, "addEventListener"));
    const removed = targets.map((target) => vi.spyOn(target, "removeEventListener"));
    const events = new Set(["online", "offline", "visibilitychange"]);
    const ours = (spy: (typeof added)[number]) =>
      spy.mock.calls.filter(([type]) => events.has(String(type))).map(([type, fn]) => [type, fn]);

    createQueryClient();
    const first = added.flatMap(ours);
    createQueryClient();

    expect(first).toHaveLength(3);
    expect(removed.flatMap(ours)).toEqual(first);
  });
});

describe("a window focused while its tab stayed visible", () => {
  it("fetches nothing: the interval already keeps it current", async () => {
    const server = serve({ [SUMMARY]: {} });
    mount(<HeaderProbe />);
    await elapse(0);

    await act(() => window.dispatchEvent(new Event("focus")));
    await elapse(0);

    expect(server.calls(SUMMARY)).toBe(1);
  });
});
