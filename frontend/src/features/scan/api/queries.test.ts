import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { invalidateSnapshot, keys } from "./queries";

describe("the Generation list in the invalidation sets", () => {
  const NAME = "opentelekomcloud-docs/ecs";

  /** A cache holding the Generation list unfiltered and under one search. */
  function cacheWithList() {
    const qc = new QueryClient();
    qc.setQueryData(keys.genList({ q: "" }), [{ name: NAME, label: "ecs" }]);
    qc.setQueryData(keys.genList({ q: "ec" }), [{ name: NAME, label: "ecs" }]);
    return qc;
  }
  const invalidated = (qc: QueryClient, q: string) => qc.getQueryState(keys.genList({ q }))?.isInvalidated;

  it("goes stale, under every search, when the active snapshot or the exclusion moves", () => {
    const qc = cacheWithList();

    invalidateSnapshot(qc, NAME);

    expect(invalidated(qc, "")).toBe(true);
    expect(invalidated(qc, "ec")).toBe(true);
  });
});
