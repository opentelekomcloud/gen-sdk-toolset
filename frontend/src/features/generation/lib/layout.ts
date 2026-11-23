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

/** "not connected" for a target that does not generate yet, or null. */
export function connectionHold(target: GenTarget): Extract<Hold, { reason: "notConnected" }> | null {
  return target.live ? null : { reason: "notConnected", target: target.label };
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
  return connectionHold(target);
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

/**
 * A resource name (ADR-0065): it becomes the package
 * `services/<service>/<version>/<name>/` of the Python SDK, so it is a
 * snake_case package name - the pattern the server checks a name against
 * (`RESOURCE_NAME_PATTERN`), held here to say so before the request goes out.
 */
export const RESOURCE_NAME = /^[a-z][a-z0-9_]*$/;

/** What is wrong with a resource name, given the names its version already has; null for nothing. */
export function nameProblem(name: string, taken: readonly string[]): "invalid" | "taken" | null {
  if (!RESOURCE_NAME.test(name)) return "invalid";
  if (taken.includes(name)) return "taken";
  return null;
}

/**
 * Where a dragged endpoint comes from: the resource it is in, or `null` for a
 * list - "unassigned" of its `version`, or "no version", where `version` is
 * `null` too.
 */
export interface EndpointSource {
  resource: number | null;
  version: string | null;
}

/**
 * Whether an endpoint may be dropped into a resource (ADR-0064). An endpoint
 * never leaves its version: from a resource or from "unassigned" only into a
 * resource of the same version, from "no version" into one of any version.
 * Dropping it where it is moves nothing. The lists are never a target: nothing
 * goes back into them.
 */
export function movable(from: EndpointSource, to: { id: number; version: string }): boolean {
  if (from.resource === to.id) return false;
  return from.version === null || from.version === to.version;
}
