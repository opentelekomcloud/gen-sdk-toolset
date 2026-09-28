/**
 * What the Generation pages read from the data hooks - and nothing more. The
 * backend for this panel does not exist yet: `mock.ts` serves these shapes from
 * memory, so a field is here only because a page reads it.
 */
import type { DocStatus } from "../../scan/types";

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
export type GenJobStatus = "running" | "done" | "merged" | "failed";

export interface GenJob {
  status: GenJobStatus;
  /** The job's pull request; null until one is open. */
  pr: number | null;
}

/** An endpoint of the service: one endpoint document of the scan. */
export interface GenEndpoint {
  id: string;
  method: string;
  uri: string;
  title: string;
  /** The document in the docs repository, at the scanned commit. */
  src: string;
  /** The document's `overall_status`. A resource holding an endpoint that is not
   *  `ok` cannot be generated (owner decision). */
  status: DocStatus;
}

/** Where a resource nobody has confirmed yet comes from: `auto` - grouped by the
 *  scanner; `new` - appeared in new docs, or made by hand in the layout (owner decision). */
export type GenOrigin = "auto" | "new";

/** A resource of a service's layout. The layout is shared by every target; the
 *  generation is not. */
export interface GenResource {
  id: string;
  /** Id of the API version the resource is laid out under. */
  version: string;
  name: string;
  /** Endpoints laid out in the resource, in order. */
  endpoints: GenEndpoint[];
  origin: GenOrigin;
  /** Who confirmed the layout of the resource; null while nobody has. */
  confirmedBy: string | null;
  /** When it was confirmed, ISO 8601; null while nobody has. */
  confirmedAt: string | null;
  /** The resource's job, keyed by `GenTarget.id`. A target without one never generated it. */
  jobs: Partial<Record<string, GenJob>>;
}

/** How an operation maps onto the SDK: a base CRUD method of the SDK's base
 *  classes, or a custom action. */
export type GenOperationKind = "base" | "custom";

/** An endpoint of a resource as the SDK will call it. */
export interface GenOperation {
  endpoint: GenEndpoint;
  kind: GenOperationKind;
  /** `list`, `get`, `create`, `update`, `delete`, or the custom action's name. */
  sdkMethod: string;
}

/** A field whose type a person has to decide before the resource can be
 *  generated (owner decision): the docs disagree on it, or give none the
 *  scanner recognizes. */
export type GenFieldProblem = "type_conflict" | "unknown_type";

export interface GenFieldIssue {
  problem: GenFieldProblem;
  /** What is wrong, in the generator's words. */
  text: string;
  /** The types to choose from, each with where it comes from. */
  options: { type: string; note: string }[];
  /** The documents that describe the field, at the scanned commit. */
  docs: { label: string; src: string }[];
  /** The type chosen, who chose it and when (ISO 8601); null while nobody has. */
  choice: { type: string; by: string; at: string } | null;
}

export interface GenField {
  name: string;
  /** The type the docs give; the scan's `Unknown` when it recognized none. */
  type: string;
  required: boolean;
  description: string;
  issue: GenFieldIssue | null;
}

/** A class the generator will emit for the resource. */
export interface GenClass {
  name: string;
  fields: GenField[];
}

/** What a resource will be generated as: its operations, in the order of its
 *  endpoints, and its classes. */
export interface GenSpec {
  operations: GenOperation[];
  classes: GenClass[];
}

/** The list's filter chips: every state still in Generation, plus `all`. */
export type GenFilter = "all" | Exclude<GenState, "done">;

/** `AttentionRule.code` of the rules the Generation panel raises. */
export type GenAttentionCode = "gen_review" | "gen_failed";
