import type { QueryClient } from "@tanstack/react-query";
import { act, fireEvent, screen } from "@testing-library/react";
import { expect, vi } from "vitest";
import { generationResources, generationServices } from "../features/generation/data/mock";
import type { GenerationServiceItem, Layout } from "../shared/api/types";
import { keys } from "../features/scan/api/queries";
import { layout, listedSeed } from "./fixtures";
import { mockFails } from "./mockFails";
import { refresh } from "./render";

/**
 * The /generation list the prototype's mock stands for: each mock service with
 * endpoints. The server never lists a service without any (ADR-0086, ADR-0087),
 * so tariff-catalog is not on it. It reads the in-memory mock, so it lives apart
 * from `fixtures.ts`, which holds the backend's answers only.
 * TODO(#150): delete with the mock once the pages read real generation data.
 */
function mockListedSeed(): [readonly unknown[], GenerationServiceItem[]] {
  const withEndpoints = generationServices().filter((s) =>
    generationResources(s.name).some((r) => r.endpoints.length > 0),
  );
  return listedSeed(...withEndpoints.map((s) => s.name));
}

/** A stored layout that exists and holds nothing. */
const STORED = layout({ versions: [], no_version: [] });

/**
 * The seeds a page of a mock service opens on: the /generation list above, and
 * a stored layout for each of its services that exists and holds nothing. The
 * pages on the mock - the card with generation switched on, the spec, the
 * result - draw the mock's resources, so nothing stored can disagree with them.
 * TODO(#150): delete with the mock once the pages read real generation data.
 */
export function mockSeeds(): [readonly unknown[], unknown][] {
  const [list, services] = mockListedSeed();
  const stored: [readonly unknown[], Layout][] = services.map((s) => [keys.genLayout(s.name), STORED]);
  return [[list, services], ...stored];
}

/**
 * The backend as the pages on the mock reach it: a read of the stored layout
 * answers the one `mockSeeds` holds. Any other request is one these suites do
 * not expect: it fails, and `others` names it, so a test can say which request
 * it was rather than only that a page failed. A test that stubs `fetch` itself
 * replaces this.
 */
export function answerStoredLayouts() {
  const others: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/layout")) return new Response(JSON.stringify(STORED));
      others.push(String(input));
      return new Response(null, { status: 500 });
    }),
  );
  return { others: () => [...others] };
}

/**
 * A Retry on a page whose resources failed to refresh over the ones it shows
 * joins the refresh already asking (ADR-0081, ADR-0084): the failure stays, not
 * the stale resources, and no second request goes out. TanStack keeps the last
 * answer through a failed refresh, which a cancelling refetch would act on. The
 * page is open on `service`, on the mock behind `withMockFails`.
 */
export async function expectRetryJoinsResources(client: QueryClient, service: string) {
  const queryKey = keys.genResources(service);
  mockFails.resources = true;
  await refresh(client, queryKey);
  expect(await screen.findByText("Failed to load service")).toBeInTheDocument();

  mockFails.resources = false;
  mockFails.holdResources = true;
  await act(async () => {
    void client.refetchQueries({ queryKey });
  });
  const asked = mockFails.resourceCalls;

  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await act(async () => {});

  expect(screen.getByText("Failed to load service")).toBeInTheDocument();
  expect(mockFails.resourceCalls).toBe(asked);
}
