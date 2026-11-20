import type { GenField, GenJob, GenResource, GenTarget } from "../data/types";

type Jobs = Partial<Record<string, GenJob>>;

/** Why a resource cannot be generated on a target. */
export type Hold =
  | { reason: "confirm" }
  | { reason: "empty" }
  | { reason: "notOk"; n: number }
  | { reason: "waitsOn"; base: string }
  | { reason: "notConnected"; target: string };

/** The reasons a resource's layout holds it back by, on every target. */
export type LayoutHold = Extract<Hold, { reason: "confirm" | "empty" | "notOk" }>;

/**
 * The first reason, in this order, the layout of a resource holds it back, or null.
 *
 * Takes plain values, as both the stored layout and the mock are asked.
 */
export function layoutHold(confirmed: boolean, statuses: readonly string[]): LayoutHold | null {
  if (!confirmed) return { reason: "confirm" };
  if (statuses.length === 0) return { reason: "empty" };
  const notOk = statuses.filter((s) => s !== "ok").length;
  if (notOk > 0) return { reason: "notOk", n: notOk };
  return null;
}

/**
 * The first reason, in this order, a resource cannot be generated on a target,
 * or null when it can. The layout's reasons come first (`layoutHold`); then a
 * target that builds on another takes a resource only once it is merged there
 * (owner decision), and only a connected target generates at all.
 */
export function holdOf(resource: GenResource, target: GenTarget, targets: GenTarget[]): Hold | null {
  const layout = layoutHold(
    resource.confirmedBy != null,
    resource.endpoints.map((e) => e.status),
  );
  if (layout) return layout;
  if (target.base != null && resource.jobs[target.base]?.status !== "merged") {
    return { reason: "waitsOn", base: targets.find((x) => x.id === target.base)?.label ?? target.base };
  }
  if (!target.live) return { reason: "notConnected", target: target.label };
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
