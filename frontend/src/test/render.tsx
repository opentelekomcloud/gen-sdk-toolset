import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { expect, vi } from "vitest";
import type { ReactElement } from "react";
import { I18nProvider } from "../shared/i18n";
import { keys } from "../features/scan/api/queries";
import type { ApiErrorEnvelope } from "../features/scan/types";

/**
 * Render a page as a signed-in user would see it.
 *
 * The session is mocked at the library boundary - `react-oidc-context` - rather
 * than at our own `useSession`, so a test that says "a viewer" really drives the
 * token through `rolesFromToken` and `canWrite` on the way to the component.
 * Mocking our own hook would test the components against a stub of the very
 * logic that decides what they show.
 *
 * Queries are seeded rather than fetched: `staleTime: Infinity` keeps the cache
 * still, so a page renders from the data the test names and nothing else.
 * A test about refreshing passes `client` - the panel's own, from
 * `createQueryClient` - because this default one never fetches again.
 */
export function renderPage(
  ui: ReactElement,
  options: { path?: string; route?: string; seed?: [readonly unknown[], unknown][]; client?: QueryClient } = {},
) {
  const client =
    options.client ??
    new QueryClient({
      defaultOptions: { queries: { staleTime: Infinity, retry: false } },
    });
  client.setQueryData(keys.summary, { scanner_version: "0.1.0", services_total: 1 });
  for (const [key, value] of options.seed ?? []) client.setQueryData(key, value);

  const { path = "/", route = "/" } = options;
  /* `client` goes back too, for a test that has to move the cache after the
     first render - a refresh failing over data it already shows, say. */
  const rendered = render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={route} element={ui} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { ...rendered, client };
}

/** Anything the page fetches beyond what the test seeded answers empty. */
export function stubEmptyApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            items: [],
            total: 0,
            page: 1,
            page_size: 20,
            doc_counts: { all: 0 },
            version_counts: {},
            counts: {},
          }),
          { status: 200 },
        ),
    ),
  );
}

export const FAILED = Symbol("the backend fails this request");
const FAILURE = { error: { code: "internal_error", message: "down" } } satisfies ApiErrorEnvelope;
/** The backend's answer that what was asked for does not exist - an answer, not a failure. */
export const NOT_FOUND = Symbol("the backend answers 404");
const MISSING = { error: { code: "not_found", message: "not found" } } satisfies ApiErrorEnvelope;

/**
 * The backend, path by path: each request is answered with what `answers`
 * holds for its path at that moment - so a test breaks the backend by setting
 * a path to FAILED, has it answer 404 with NOT_FOUND, holds an answer back by
 * setting a promise there, or answers request by request through a function.
 */
export function backend(answers: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).split("?")[0];
    const entry = answers[path];
    const answer = await (typeof entry === "function" ? entry() : entry);
    if (answer === FAILED) return new Response(JSON.stringify(FAILURE), { status: 500 });
    if (answer === NOT_FOUND) return new Response(JSON.stringify(MISSING), { status: 404 });
    return new Response(JSON.stringify(answer ?? null));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls: (path: string) => fetchMock.mock.calls.filter(([input]) => String(input).split("?")[0] === path).length };
}

/** A refresh, as the periodic one or an invalidation runs it. */
export const refresh = (client: QueryClient, key: readonly unknown[]) => act(() => client.invalidateQueries({ queryKey: key }));

/** The alert that says `text` - announced, and holding its own Retry. */
export async function alertNamed(text: string): Promise<HTMLElement> {
  const alert = (await screen.findByText(text)).closest<HTMLElement>("[role=alert]");
  expect(alert).not.toBeNull();
  return alert as HTMLElement;
}

/** The periodic refresh of `keys`: no click, and time for TanStack to tell the components. */
export const pollAgain = (client: QueryClient, ...queryKeys: (readonly unknown[])[]) =>
  act(async () => {
    for (const queryKey of queryKeys) void client.refetchQueries({ queryKey });
    await new Promise((resolve) => setTimeout(resolve, 20));
  });

/** An answer the test sends when it chooses; until then the request is under way. */
export function later() {
  let send: (body: unknown) => void = () => {};
  const arrived = new Promise((resolve) => (send = resolve));
  return { arrived, send };
}
