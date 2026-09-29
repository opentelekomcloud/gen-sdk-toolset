import type { GenField, GenJob, GenResource, GenTarget } from "../data/types";

type Jobs = Partial<Record<string, GenJob>>;

/** Why a resource cannot be generated on a target. */
export type Hold =
  | { reason: "confirm" }
  | { reason: "empty" }
  | { reason: "notOk"; n: number }
  | { reason: "waitsOn"; base: string }
  | { reason: "notConnected" };

/**
 * The first reason, in this order, a resource cannot be generated on a target,
 * or null when it can. Its layout has to be confirmed, hold endpoints and every
 * one of their documents `ok` (owner decision); a target that builds on another
 * takes a resource only once it is merged there (owner decision), and only a
 * connected target generates at all. `base` is the base target's label.
 */
export function holdOf(resource: GenResource, target: GenTarget, targets: GenTarget[]): Hold | null {
  const notOk = resource.endpoints.filter((e) => e.status !== "ok").length;
  if (resource.confirmedBy == null) return { reason: "confirm" };
  if (resource.endpoints.length === 0) return { reason: "empty" };
  if (notOk > 0) return { reason: "notOk", n: notOk };
  if (target.base != null && resource.jobs[target.base]?.status !== "merged") {
    return { reason: "waitsOn", base: targets.find((x) => x.id === target.base)?.label ?? target.base };
  }
  if (!target.live) return { reason: "notConnected" };
  return null;
}

/** A field whose problem nobody has decided yet: its resource is not generated until someone does (owner decision). */
export const undecided = (f: GenField) => f.issue != null && f.issue.choice == null;

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
