import { generationResources, generationServices } from "../features/generation/data/mock";
import type { GenerationServiceItem } from "../shared/api/types";
import { listedSeed } from "./fixtures";

/**
 * The /generation list the prototype's mock stands for: each mock service with
 * endpoints. The server never lists a service without any (ADR-0086, ADR-0087),
 * so tariff-catalog is not on it. It reads the in-memory mock, so it lives apart
 * from `fixtures.ts`, which holds the backend's answers only.
 * TODO(#150): delete with the mock once the pages read real generation data.
 */
export function mockListedSeed(): [readonly unknown[], GenerationServiceItem[]] {
  const withEndpoints = generationServices().filter((s) =>
    generationResources(s.name).some((r) => r.endpoints.length > 0),
  );
  return listedSeed(...withEndpoints.map((s) => s.name));
}
