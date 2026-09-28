import type { GenJob, GenTarget } from "../data/types";

type Jobs = Partial<Record<string, GenJob>>;

/**
 * The job that freezes a resource's layout, or null. The layout is shared by
 * every target, so a resource generating or waiting for review on any of them
 * must not move: its generated code was made from this layout. A failed job
 * wrote nothing and freezes nothing.
 */
export function lockingJob(jobs: Jobs, targets: GenTarget[]): { target: GenTarget; job: GenJob } | null {
  for (const target of targets) {
    const job = jobs[target.id];
    if (job?.status === "running" || job?.status === "done") return { target, job };
  }
  return null;
}

/**
 * Merged on every connected target: the resource has left the layout for
 * Maintenance. With no target connected nothing can have been merged, so
 * nothing has left.
 */
export function mergedEverywhere(jobs: Jobs, targets: GenTarget[]): boolean {
  const live = targets.filter((t) => t.live);
  return live.length > 0 && live.every((t) => jobs[t.id]?.status === "merged");
}
