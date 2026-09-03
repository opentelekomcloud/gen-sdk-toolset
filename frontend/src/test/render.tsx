import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";
import type { ReactElement } from "react";
import { I18nProvider } from "../shared/i18n";
import { keys } from "../features/scan/api/queries";

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
 */
export function renderPage(
  ui: ReactElement,
  options: { path?: string; route?: string; seed?: [readonly unknown[], unknown][] } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  });
  client.setQueryData(keys.summary, { scanner_version: "0.1.0", services_total: 1 });
  for (const [key, value] of options.seed ?? []) client.setQueryData(key, value);

  const { path = "/", route = "/" } = options;
  return render(
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
