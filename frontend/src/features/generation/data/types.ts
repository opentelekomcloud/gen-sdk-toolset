/**
 * What the Generation pages read from the data hooks - and nothing more. The
 * backend for this panel does not exist yet: `mock.ts` serves these shapes from
 * memory, so a field is here only because a page reads it.
 */

/** An edition built from the shared structure of a service (Python SDK, Ansible modules). */
export interface GenTarget {
  id: string;
  label: string;
  /** Connected: generation runs for this target. */
  live: boolean;
  /** The target this one builds on - a resource generates here only once merged there. */
  base: string | null;
}

/**
 * Where a service stands on one target, derived from the generation state of
 * its resources there. `done` means every resource is merged.
 */
export type GenState = "not_generated" | "in_progress" | "failed" | "review" | "partial" | "done";

export interface GenTargetSummary {
  state: GenState;
  /** Resources merged on this target. */
  merged: number;
  /** Resources of the service. */
  total: number;
}

/** A service in Generation: scan status `scanned` or `partial`. */
export interface GenService {
  name: string;
  /** Keyed by `GenTarget.id`. */
  targets: Record<string, GenTargetSummary>;
}

/** The list's filter chips: every state still in Generation, plus `all`. */
export type GenFilter = "all" | Exclude<GenState, "done">;

/** `AttentionRule.code` of the rules the Generation panel raises. */
export type GenAttentionCode = "gen_review" | "gen_failed";
