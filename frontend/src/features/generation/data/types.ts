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
  /** Repository the target's pull requests are opened in. */
  repo: string;
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

/** A resource's generation job on one target. `done` is a job whose pull request
 *  is open and waiting for review; `merged` is one whose pull request was merged. */
export type JobStatus = "running" | "done" | "merged" | "failed";

export interface GenJob {
  status: JobStatus;
  /** The job's pull request; null until one is open. */
  pr: number | null;
}

/** A resource of a service's layout. The layout is shared by every target; the
 *  generation is not. */
export interface GenResource {
  id: string;
  /** Id of the API version the resource is laid out under. */
  version: string;
  name: string;
  /** Endpoints laid out in the resource. */
  endpoints: number;
  /** Of those, the endpoints whose document's `overall_status` is not `ok`. A
   *  resource holding one cannot be generated (owner decision). */
  notOk: number;
  /** Who confirmed the layout of the resource; null while nobody has. */
  confirmedBy: string | null;
  /** The resource's job, keyed by `GenTarget.id`. A target without one never generated it. */
  jobs: Partial<Record<string, GenJob>>;
}

/** The list's filter chips: every state still in Generation, plus `all`. */
export type GenFilter = "all" | Exclude<GenState, "done">;

/** `AttentionRule.code` of the rules the Generation panel raises. */
export type GenAttentionCode = "gen_review" | "gen_failed";
