import type * as GenerationMock from "../features/generation/data/mock";

const OFF = {
  /** The targets throw. */
  targets: false,
  /** The targets come, but none of them. */
  noTargets: false,
  /** The targets never come. */
  holdTargets: false,
  /** The resources throw. */
  resources: false,
  /** The resources never come. */
  holdResources: false,
  /**
   * How often the mock's resources were read - by the page, and by a test that
   * reads them itself; compare it around one step, not as a total.
   */
  resourceCalls: 0,
};

/**
 * Switches for the Generation pages' in-memory mock, for the tests that make
 * its targets or resources fail, come empty or never come. Set in a test, they
 * are reset after every test by `setup.ts`, so none leaks into the next.
 * TODO(#150): delete with the mock once the pages read real generation data.
 */
export const mockFails = { ...OFF };

export function resetMockFails() {
  Object.assign(mockFails, OFF);
}

/**
 * The mock with its targets and resources behind `mockFails`; everything else
 * as it is. A `vi.mock` factory is hoisted above the file's imports, so it
 * imports this module itself:
 *
 *     vi.mock("../data/mock", async (importOriginal) =>
 *       (await import("../../../test/mockFails")).withMockFails(await importOriginal<typeof import("../data/mock")>()),
 *     );
 */
export function withMockFails(mock: typeof GenerationMock) {
  return {
    ...mock,
    generationTargets: () => {
      if (mockFails.targets) throw new Error("targets unavailable");
      if (mockFails.noTargets) return [];
      if (mockFails.holdTargets) return new Promise<never>(() => {});
      return mock.generationTargets();
    },
    generationResources: (service: string) => {
      mockFails.resourceCalls += 1;
      if (mockFails.resources) throw new Error("layout store unavailable");
      if (mockFails.holdResources) return new Promise<never>(() => {});
      return mock.generationResources(service);
    },
  };
}
