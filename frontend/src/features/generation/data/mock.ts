/**
 * In-memory stand-in for the Generation backend, which does not exist yet. The
 * hooks in `queries.ts` read it; nothing else may. Data is the prototype's
 * (`TARGETS`, `AUTO_STRUCTURE`, `JOB_SEED`, `CONFIRM_SEED`); service names are
 * those of `mock/scanApi.ts`.
 */
import type { AttentionRule } from "../../../shared/api/types";
import type { DocStatus } from "../../scan/types";
import type {
  GenAttentionCode,
  GenJob,
  GenJobStatus,
  GenResource,
  GenService,
  GenState,
  GenTarget,
  GenTargetSummary,
} from "./types";

const TARGETS: GenTarget[] = [
  { id: "python", label: "Python SDK", live: true, base: null, repo: "opentelekomcloud/python-t-cloud" },
  {
    id: "ansible",
    label: "Ansible modules",
    live: false,
    base: "python",
    repo: "opentelekomcloud/ansible-collection-cloud",
  },
];

interface LaidOut {
  id: string;
  version: string;
  name: string;
  /** As `METHOD uri`. */
  endpoints: string[];
  /** From the prototype's `CONFIRM_SEED`, not its `origin`: a layout is confirmed
   *  when the confirmation is recorded (owner decision). */
  confirmedBy: string | null;
}

/**
 * The layout of every service in Generation - the scan mock's services with scan
 * status `scanned` or `partial` (owner decision). The prototype has no layout for
 * device-mgmt and none for tariff-catalog, which has no endpoints.
 */
const LAYOUT: Record<string, LaidOut[]> = {
  "billing-api": [
    {
      id: "v1_invoices",
      version: "v1",
      name: "invoices",
      confirmedBy: "valeriia",
      endpoints: [
        "GET /v1/billing/invoices",
        "GET /v1/billing/invoices/{invoice_id}",
        "POST /v1/billing/invoices",
        "DELETE /v1/billing/invoices/{invoice_id}",
      ],
    },
    {
      id: "v1_payments",
      version: "v1",
      name: "payments",
      confirmedBy: null,
      endpoints: ["GET /v1/billing/payments", "POST /v1/billing/payments", "PUT /v1/billing/payments/{payment_id}"],
    },
    {
      id: "v1_misc",
      version: "v1",
      name: "misc",
      confirmedBy: null,
      endpoints: ["GET /v1/billing/credit-notes", "GET /v1/billing/credit-notes/{note_id}", "GET /v1/billing/quotas"],
    },
    {
      id: "v2_invoices",
      version: "v2",
      name: "invoices",
      confirmedBy: null,
      endpoints: ["GET /v2/billing/invoices", "POST /v2/billing/invoices/export"],
    },
  ],
  "customer-core": [
    {
      id: "c_customers",
      version: "v1",
      name: "customers",
      confirmedBy: "ivan",
      endpoints: [
        "GET /v1/customers",
        "GET /v1/customers/{customer_id}",
        "PUT /v1/customers/{customer_id}",
        "DELETE /v1/customers/{customer_id}",
      ],
    },
    {
      id: "c_contacts",
      version: "v1",
      name: "contacts",
      confirmedBy: null,
      endpoints: ["GET /v1/customers/{customer_id}/contacts", "POST /v1/customers/{customer_id}/contacts"],
    },
    {
      id: "c_addresses",
      version: "v1",
      name: "addresses",
      confirmedBy: null,
      endpoints: [
        "GET /v1/customers/{customer_id}/addresses",
        "PATCH /v1/customers/{customer_id}/addresses/{address_id}",
      ],
    },
  ],
  "device-mgmt": [],
  "notifications-hub": [
    {
      id: "n_topics",
      version: "v1",
      name: "topics",
      confirmedBy: "valeriia",
      endpoints: ["GET /v1/notifications/topics", "POST /v1/notifications/topics", "DELETE /v1/notifications/topics/{topic_urn}"],
    },
    {
      id: "n_subscriptions",
      version: "v1",
      name: "subscriptions",
      confirmedBy: null,
      endpoints: ["GET /v1/notifications/subscriptions", "POST /v1/notifications/subscriptions"],
    },
  ],
  "tariff-catalog": [],
};

/** `overall_status` of the endpoint documents that are not `ok`; every other one
 *  is. The prototype has no such endpoint, so the mock makes one. */
const DOC_STATUS: Record<string, DocStatus> = { "GET /v1/billing/quotas": "partial" };

/** Jobs by target id, then resource id. A resource without one was never generated there. */
const JOBS: Record<string, Record<string, GenJob>> = {
  python: {
    v1_invoices: { status: "done", pr: 131 },
    c_contacts: { status: "failed", pr: null },
    n_topics: { status: "merged", pr: 118 },
    c_customers: { status: "merged", pr: 122 },
  },
};

function summarize(resources: string[], target: string): GenTargetSummary {
  const jobs = JOBS[target] ?? {};
  const count = (status: GenJobStatus) => resources.filter((r) => jobs[r]?.status === status).length;
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

const resourceIds = (name: string) => LAYOUT[name].map((r) => r.id);

export function generationTargets(): GenTarget[] {
  return TARGETS.map((t) => ({ ...t }));
}

export function generationServices(): GenService[] {
  return Object.keys(LAYOUT).map((name) => ({
    name,
    targets: Object.fromEntries(TARGETS.map((t) => [t.id, summarize(resourceIds(name), t.id)])),
  }));
}

/** The layout of one service, in order, with each resource's job on every target. */
export function generationResources(service: string): GenResource[] {
  const layout = LAYOUT[service];
  if (!layout) throw new Error(`${service} is not in Generation`);
  return layout.map((r) => ({
    id: r.id,
    version: r.version,
    name: r.name,
    endpoints: r.endpoints.length,
    notOk: r.endpoints.filter((e) => (DOC_STATUS[e] ?? "ok") !== "ok").length,
    confirmedBy: r.confirmedBy,
    jobs: Object.fromEntries(
      TARGETS.flatMap((t) => {
        const job = JOBS[t.id]?.[r.id];
        return job ? [[t.id, { ...job }]] : [];
      }),
    ),
  }));
}

/** The panel's rules for the shared attention band: resources waiting for review
 *  and resources whose generation failed, over every connected target. */
export function generationAttention(): AttentionRule[] {
  const live = TARGETS.filter((t) => t.live);
  const resources = Object.keys(LAYOUT).flatMap(resourceIds);
  const tally = (status: GenJobStatus) =>
    live.reduce((n, t) => n + resources.filter((r) => JOBS[t.id]?.[r]?.status === status).length, 0);
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
