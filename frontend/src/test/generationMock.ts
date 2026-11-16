import { vi } from "vitest";
import { generationResources, generationServices } from "../features/generation/data/mock";
import type { GenerationServiceItem, Layout } from "../shared/api/types";
import { keys } from "../features/scan/api/queries";
import { layout, listedSeed } from "./fixtures";

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

/** A stored layout that exists and holds nothing: the editor draws the mock's. */
const STORED = layout({ versions: [], no_version: [] });

/**
 * The seeds a page of a mock service opens on: the /generation list above, and
 * a stored layout for each of its services, so the layout page shows its editor
 * rather than the empty state. The editor still draws the mock's resources
 * (ISS-0042), so the stored layout says only that there is one, and holds
 * nothing that could disagree with what the editor shows.
 * TODO(#150): delete with the mock once the pages read real generation data.
 */
export function mockSeeds(): [readonly unknown[], unknown][] {
  const [list, services] = mockListedSeed();
  const stored: [readonly unknown[], Layout][] = services.map((s) => [keys.genLayout(s.name), STORED]);
  return [[list, services], ...stored];
}

/**
 * The backend as the layout editor reaches it: every edit asks for the stored
 * layout again, and it answers the one `mockSeeds` holds. Any other request is
 * one these suites do not expect: it fails, and `others` names it, so a test
 * can say which request it was rather than only that a page failed. A test that
 * stubs `fetch` itself replaces this.
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
