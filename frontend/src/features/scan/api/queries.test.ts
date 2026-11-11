import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { invalidateGenLayout, invalidateSnapshot, keys } from "./queries";
import { layout } from "../../../test/fixtures";

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

describe("the layout of a service in the invalidation sets", () => {
  const NAME = "opentelekomcloud-docs/ecs";
  const OTHER = "opentelekomcloud-docs/vpc";

  it("goes stale after an edit of that service's layout, and only that service's", () => {
    const qc = new QueryClient();
    qc.setQueryData(keys.genLayout(NAME), layout());
    qc.setQueryData(keys.genLayout(OTHER), layout());

    invalidateGenLayout(qc, NAME);

    expect(qc.getQueryState(keys.genLayout(NAME))?.isInvalidated).toBe(true);
    expect(qc.getQueryState(keys.genLayout(OTHER))?.isInvalidated).toBe(false);
  });
});
