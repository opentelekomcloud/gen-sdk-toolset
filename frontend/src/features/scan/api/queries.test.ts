import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import type { Job, JobStatus } from "../../../shared/api/types";
import { JOB_TERMINAL, invalidateScanFailure, invalidateSnapshot, jobRefetchInterval, keys } from "./queries";

function makeJob(status: JobStatus): Job {
  return {
    id: 1,
    service_id: 1,
    repository: "elb-api",
    kind: "scan",
    status,
    scanner_version: null,
    commit_hash: null,
    error: null,
    created_at: "2026-07-24T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

describe("jobRefetchInterval", () => {
  it("keeps polling while the job is queued or running", () => {
    expect(jobRefetchInterval(makeJob("queued"))).toBe(1500);
    expect(jobRefetchInterval(makeJob("running"))).toBe(1500);
  });

  it("stops polling once the job is terminal", () => {
    expect(jobRefetchInterval(makeJob("done"))).toBe(false);
    expect(jobRefetchInterval(makeJob("failed"))).toBe(false);
  });

  it("keeps polling until the first response arrives", () => {
    expect(jobRefetchInterval(undefined)).toBe(1500);
  });

  it("treats exactly done and failed as terminal", () => {
    expect([...JOB_TERMINAL].sort()).toEqual(["done", "failed"]);
  });
});

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

  it("stays as it is after a failed scan, which leaves the active snapshot in place", () => {
    const qc = cacheWithList();

    invalidateScanFailure(qc, NAME);

    expect(invalidated(qc, "")).toBe(false);
    expect(invalidated(qc, "ec")).toBe(false);
  });
});
