import { describe, expect, it } from "vitest";
import type { Job, JobStatus } from "./types.local";
import { JOB_TERMINAL, jobRefetchInterval } from "./queries";

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

describe("jobRefetchInterval (F8 polling policy)", () => {
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
