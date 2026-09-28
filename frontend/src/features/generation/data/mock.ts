/**
 * In-memory stand-in for the Generation backend, which does not exist yet. The
 * hooks in `queries.ts` read it; nothing else may. Data is the prototype's
 * (`TARGETS`, `AUTO_STRUCTURE`, `JOB_SEED`); service names are those of
 * `mock/scanApi.ts`.
 */
import type { AttentionRule } from "../../../shared/api/types";
import type { GenAttentionCode, GenService, GenState, GenTarget, GenTargetSummary } from "./types";

/** A resource's generation job on one target. `done` is a job whose pull request
 *  is open and waiting for review; `merged` is one whose pull request was merged. */
type JobStatus = "running" | "done" | "merged" | "failed";

const TARGETS: GenTarget[] = [
  { id: "python", label: "Python SDK", live: true, base: null },
  { id: "ansible", label: "Ansible modules", live: false, base: "python" },
];

/**
 * Resource ids of every service in Generation - the scan mock's services with
 * scan status `scanned` or `partial` (owner decision). The prototype has no
 * layout for device-mgmt and none for tariff-catalog, which has no endpoints.
 */
const RESOURCES: Record<string, string[]> = {
  "billing-api": ["v1_invoices", "v1_payments", "v1_misc", "v2_invoices"],
  "customer-core": ["c_customers", "c_contacts", "c_addresses"],
  "device-mgmt": [],
  "notifications-hub": ["n_topics", "n_subscriptions"],
  "tariff-catalog": [],
};

/** Jobs by target id, then resource id. A resource without one was never generated there. */
const JOBS: Record<string, Record<string, JobStatus>> = {
  python: { v1_invoices: "done", c_contacts: "failed", n_topics: "merged", c_customers: "merged" },
};

function summarize(resources: string[], target: string): GenTargetSummary {
  const jobs = JOBS[target] ?? {};
  const count = (status: JobStatus) => resources.filter((r) => jobs[r] === status).length;
  const merged = count("merged");
  const untouched = resources.filter((r) => !jobs[r]).length;
  const state: GenState = !resources.length
    ? "not_generated"
    : count("running")
      ? "in_progress"
      : count("failed")
        ? "failed"
        : count("done")
          ? "review"
          : merged && untouched
            ? "partial"
            : merged
              ? "done"
              : "not_generated";
  return { state, merged, total: resources.length };
}

export function generationTargets(): GenTarget[] {
  return TARGETS.map((t) => ({ ...t }));
}

export function generationServices(): GenService[] {
  return Object.entries(RESOURCES).map(([name, resources]) => ({
    name,
    targets: Object.fromEntries(TARGETS.map((t) => [t.id, summarize(resources, t.id)])),
  }));
}

/** The panel's rules for the shared attention band: resources waiting for review
 *  and resources whose generation failed, over every connected target. */
export function generationAttention(): AttentionRule[] {
  const live = TARGETS.filter((t) => t.live);
  const resources = Object.values(RESOURCES).flat();
  const tally = (status: JobStatus) =>
    live.reduce((n, t) => n + resources.filter((r) => JOBS[t.id]?.[r] === status).length, 0);
  const rule = (code: GenAttentionCode, label: string, count: number): AttentionRule => ({
    code,
    panel: "generation",
    label,
    count,
  });
  return [
    rule("gen_review", "generated, waiting for review", tally("done")),
    rule("gen_failed", "generation failed — LLM unavailable", tally("failed")),
  ].filter((r) => r.count > 0);
}
