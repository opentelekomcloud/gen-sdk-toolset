import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useDocumentDetail, useServices, useSnapshots, useSummary } from "../../features/scan/api/queries";
import { createQueryClient, REFETCH_INTERVAL_MS } from "./queryClient";

const NAME = "opentelekomcloud-docs/vpc";
const SUMMARY = "/api/scan/summary";
const SERVICES = "/api/scan/services";
const DOCUMENT = `/api/scan/services/${encodeURIComponent(NAME)}/documents/3`;
const SNAPSHOTS = `/api/scan/services/${encodeURIComponent(NAME)}/snapshots`;
/** The longest a visible tab may take to show a change saved on the server (ADR-0077). */
const DEADLINE_MS = 15_000;

/**
 * The server as the tab sees it: each path answers with whatever `state` holds
 * for it at the moment of the request, so a test changes the server by
 * assigning to `state`.
 */
function serve(state: Record<string, unknown>) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => new Response(JSON.stringify(state[String(input)] ?? null)));
  vi.stubGlobal("fetch", fetchMock);
  return { calls: (path: string) => fetchMock.mock.calls.filter(([input]) => String(input) === path).length };
}

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
  return { rerender: (node: ReactNode) => rendered.rerender(wrap(node)) };
}

/** Lets the clock run - each refetch fires and its answer lands - without waiting it out. */
const elapse = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const shown = (id: string) => screen.getByTestId(id).textContent;

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
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
