import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen } from "@testing-library/react";
import type { Job, JobStatus } from "../../../shared/api/types";
import { renderPage } from "../../../test/render";
import { jobRefetchInterval, keys, useJob } from "../api/queries";
import { ScanJobWatcher } from "./ScanJobWatcher";

const NAME = "opentelekomcloud-docs/vpc";
const LIST = [{ name: NAME, label: "vpc" }];
/** The job poll's cadence while a job runs. */
const POLL = jobRefetchInterval(undefined) as number;
/** A little past one poll, so its answer has been handed to the components too. */
const NEXT_POLL = POLL + 50;

/**
 * Job 7 as the backend reports it. Answers differ only where their status or
 * `finished_at` does - two equal answers reach the watcher as one object, and
 * its effect does not run again for the second.
 */
function job(status: JobStatus, finished_at: string | null = null): Job {
  return {
    id: 7,
    service_id: 1,
    repository: NAME,
    kind: "scan",
    status,
    scanner_version: null,
    commit_hash: null,
    error: status === "failed" ? "clone failed" : null,
    created_at: "2026-11-04T10:00:00Z",
    started_at: status === "queued" ? null : "2026-11-04T10:00:01Z",
    finished_at: status === "done" || status === "failed" ? (finished_at ?? "2026-11-04T10:00:09Z") : null,
  };
}

/** What the page shows of job 7: proof an answer reached the components, not only the cache. */
function JobProbe() {
  const { data } = useJob(7);
  return <output data-testid="job">{data ? `${data.status} ${data.finished_at}` : ""}</output>;
}

/**
 * A watcher for job 7 beside a cached Generation list and summary. The job is
 * not seeded: every status reaches the watcher through a poll, one answer per
 * request, the last repeated.
 */
function watch(...answers: Job[]) {
  let n = 0;
  const fetchMock = vi.fn<typeof fetch>(async (input) =>
    String(input) === "/api/jobs/7"
      ? new Response(JSON.stringify(answers[Math.min(n++, answers.length - 1)]))
      : new Response(JSON.stringify([])),
  );
  vi.stubGlobal("fetch", fetchMock);
  const { client } = renderPage(
    <>
      <ScanJobWatcher serviceName={NAME} jobId={7} />
      <JobProbe />
    </>,
    {
      seed: [[keys.genList({ q: "" }), LIST]],
    },
  );
  return {
    client,
    jobPolls: () => fetchMock.mock.calls.filter(([input]) => String(input) === "/api/jobs/7").length,
    listInvalidated: () => client.getQueryState(keys.genList({ q: "" }))?.isInvalidated,
    summaryInvalidated: () => client.getQueryState(keys.summary)?.isInvalidated,
    rendered: () => screen.getByTestId("job").textContent,
  };
}

/** Lets the clock run - each poll fires and its answer lands - without waiting it out. */
const elapse = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the Generation list after a scan this tab watched", () => {
  it("is left alone while the scan is queued and running, and goes stale once it is done", async () => {
    const { jobPolls, listInvalidated, summaryInvalidated, rendered } = watch(
      job("queued"),
      job("running"),
      job("done"),
    );

    await elapse(0);
    expect(rendered()).toBe("queued null");
    expect(listInvalidated()).toBe(false);

    await elapse(NEXT_POLL);
    expect(jobPolls()).toBe(2);
    expect(rendered()).toBe("running null");
    expect(listInvalidated()).toBe(false);
    expect(summaryInvalidated()).toBe(false);

    await elapse(NEXT_POLL);

    expect(jobPolls()).toBe(3);
    expect(rendered()).toContain("done");
    expect(listInvalidated()).toBe(true);
    // the list goes with the service's own views: one invalidation set, not a second path
    expect(summaryInvalidated()).toBe(true);
  });

  it("stays as it is when the scan failed, which leaves the active snapshot in place", async () => {
    const { listInvalidated, summaryInvalidated, rendered } = watch(job("running"), job("failed"));

    await elapse(0);
    expect(summaryInvalidated()).toBe(false);

    await elapse(NEXT_POLL);

    expect(rendered()).toContain("failed");
    // the failure did reach the cache - the summary surfaces it - and the list was left alone
    expect(summaryInvalidated()).toBe(true);
    expect(listInvalidated()).toBe(false);
  });

  it("refreshes once per scan, however often the finished job is read again", async () => {
    // A finished job can still be fetched again - on window focus, say - and the
    // new answer differs from the first. Refreshing on it would refetch every
    // view of the service for a scan already accounted for.
    const { client, listInvalidated, rendered } = watch(job("done"), job("done", "2026-11-04T10:00:10Z"));
    await elapse(0);
    expect(listInvalidated()).toBe(true);
    client.setQueryData(keys.genList({ q: "" }), LIST);

    await act(() => client.refetchQueries({ queryKey: keys.job(7) }));
    // TanStack hands a new answer to the component on a zero-delay timer
    await elapse(0);

    expect(rendered()).toContain("2026-11-04T10:00:10Z");
    expect(listInvalidated()).toBe(false);
  });
});

describe("the job poll the watcher runs", () => {
  it("stops polling once the scan is over", async () => {
    const { jobPolls } = watch(job("running"), job("done"));

    await elapse(POLL * 4);

    expect(jobPolls()).toBe(2);
  });
});
