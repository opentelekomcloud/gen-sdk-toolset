/**
 * In-memory stand-in for the Generation backend, which does not exist yet. The
 * hooks in `queries.ts` and `mutations.ts` read and change it; nothing else may,
 * except a test putting it back with `resetGenerationMock`. Data is the
 * prototype's (`TARGETS`, `AUTO_STRUCTURE`, `JOB_SEED`, `CONFIRM_SEED`,
 * `ENTITIES`, `QUERY_IR`, `QUERY_EXTRA`, the settings); service names are those
 * of `mock/scanApi.ts`. It stands in for GitHub and OTC as well: a pull request's
 * state and a live call's answer come from here.
 */
import type { AttentionRule } from "../../../shared/api/types";
import type { DocStatus } from "../../scan/types";
import { holdOf, lockingJob, mergedEverywhere, type Hold } from "../lib/layout";
import { pathParams } from "../lib/uri";
import type {
  GenAttentionCode,
  GenEndpoint,
  GenFieldProblem,
  GenJob,
  GenJobStatus,
  GenLiveResponse,
  GenOperation,
  GenOrigin,
  GenResource,
  GenService,
  GenSpec,
  GenState,
  GenTarget,
  GenTargetSummary,
  OtcCheck,
  OtcSettings,
  OtcSettingsForm,
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

interface Endpoint {
  id: string;
  method: string;
  uri: string;
  title: string;
  /** The document's path under `api-ref/source`. */
  file: string;
  status: DocStatus;
}

/** An endpoint document; its `overall_status` is `ok` unless given. */
const ep = (id: string, method: string, uri: string, title: string, file: string, status: DocStatus = "ok"): Endpoint => ({
  id,
  method,
  uri,
  title,
  file,
  status,
});

interface LaidOut {
  id: string;
  version: string;
  name: string;
  origin: GenOrigin;
  endpoints: Endpoint[];
  /** From the prototype's `CONFIRM_SEED`, not its `origin`: a layout is confirmed
   *  when the confirmation is recorded (owner decision). So the prototype's
   *  `confirmed` origin is `auto` here, and n_topics, `auto` there, is confirmed. */
  confirmed: { by: string; at: string } | null;
}

/**
 * The layout the scanner proposed for every service in Generation - the scan
 * mock's services with scan status `scanned` or `partial` (owner decision) -
 * with the confirmations recorded before. "Reset to auto" goes back to it. The
 * prototype has no layout for device-mgmt, which it does not have in Generation:
 * it is given one (owner decision) from its 31 documents in the scan mock, with
 * their statuses there - 18 ok, 9 partial, 4 failed. tariff-catalog has no
 * endpoints, so no layout.
 */
const AUTO: Record<string, LaidOut[]> = {
  "billing-api": [
    {
      id: "v1_invoices",
      version: "v1",
      name: "invoices",
      origin: "auto",
      confirmed: { by: "valeriia", at: "2026-08-11T13:58:00Z" },
      endpoints: [
        ep("e1", "GET", "/v1/billing/invoices", "List invoices of a project", "invoices/list-invoices.rst"),
        ep("e2", "GET", "/v1/billing/invoices/{invoice_id}", "Query invoice details", "invoices/show-invoice.rst"),
        ep("e3", "POST", "/v1/billing/invoices", "Create a manual invoice", "invoices/create-invoice.rst"),
        ep("e4", "DELETE", "/v1/billing/invoices/{invoice_id}", "Cancel an invoice", "invoices/cancel-invoice.rst"),
      ],
    },
    {
      id: "v1_payments",
      version: "v1",
      name: "payments",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("e5", "GET", "/v1/billing/payments", "List payments", "payments/list-payments.rst"),
        ep("e6", "POST", "/v1/billing/payments", "Submit a payment", "payments/create-payment.rst"),
        ep("e7", "PUT", "/v1/billing/payments/{payment_id}", "Update payment method", "payments/update-payment.rst"),
      ],
    },
    {
      id: "v1_misc",
      version: "v1",
      name: "misc",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("e8", "GET", "/v1/billing/credit-notes", "List credit notes", "credit-notes/list-credit-notes.rst"),
        ep("e9", "GET", "/v1/billing/credit-notes/{note_id}", "Query a credit note", "credit-notes/show-credit-note.rst"),
        /* The prototype has no endpoint whose document is not ok, so the mock makes one. */
        ep("e10", "GET", "/v1/billing/quotas", "Query billing quotas", "quotas/show-quotas.rst", "partial"),
      ],
    },
    {
      id: "v2_invoices",
      version: "v2",
      name: "invoices",
      origin: "new",
      confirmed: null,
      endpoints: [
        ep("e11", "GET", "/v2/billing/invoices", "List invoices (v2)", "v2/invoices/list-invoices.rst"),
        ep("e12", "POST", "/v2/billing/invoices/export", "Export invoices as CSV", "v2/invoices/export-invoices.rst"),
      ],
    },
  ],
  "customer-core": [
    {
      id: "c_customers",
      version: "v1",
      name: "customers",
      origin: "auto",
      confirmed: { by: "ivan", at: "2026-08-10T16:31:00Z" },
      endpoints: [
        ep("c1", "GET", "/v1/customers", "List customers", "customers/list-customers.rst"),
        ep("c2", "GET", "/v1/customers/{customer_id}", "Query customer details", "customers/show-customer.rst"),
        ep("c3", "PUT", "/v1/customers/{customer_id}", "Update a customer", "customers/update-customer.rst"),
        ep("c4", "DELETE", "/v1/customers/{customer_id}", "Delete a customer", "customers/delete-customer.rst"),
      ],
    },
    {
      id: "c_contacts",
      version: "v1",
      name: "contacts",
      origin: "auto",
      /* Not in `CONFIRM_SEED`, yet the prototype's `JOB_SEED` has ivan generate it: a
       * generation cannot start unconfirmed, so ivan confirmed it before (owner decision). */
      confirmed: { by: "ivan", at: "2026-08-12T07:58:00Z" },
      endpoints: [
        ep("c5", "GET", "/v1/customers/{customer_id}/contacts", "List contacts of a customer", "contacts/list-contacts.rst"),
        ep("c6", "POST", "/v1/customers/{customer_id}/contacts", "Add a contact", "contacts/create-contact.rst"),
      ],
    },
    {
      id: "c_addresses",
      version: "v1",
      name: "addresses",
      origin: "new",
      confirmed: null,
      endpoints: [
        ep("c7", "GET", "/v1/customers/{customer_id}/addresses", "List addresses", "addresses/list-addresses.rst"),
        ep(
          "c8",
          "PATCH",
          "/v1/customers/{customer_id}/addresses/{address_id}",
          "Update an address",
          "addresses/update-address.rst",
        ),
      ],
    },
  ],
  "device-mgmt": [
    {
      id: "d_devices",
      version: "v2",
      name: "devices",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("d1", "GET", "/v2/devices", "List devices", "devices/list-devices.rst"),
        ep("d2", "GET", "/v2/devices/{device_id}", "Query device details", "devices/show-device.rst"),
        ep("d3", "POST", "/v2/devices", "Register a device", "devices/create-device.rst", "partial"),
        ep("d4", "PUT", "/v2/devices/{device_id}", "Update a device", "devices/update-device.rst", "partial"),
        ep("d5", "DELETE", "/v2/devices/{device_id}", "Delete a device", "devices/delete-device.rst"),
        ep(
          "d6",
          "POST",
          "/v2/devices/{device_id}/action",
          "Reset a device secret",
          "devices/reset-device-secret.rst",
          "partial",
        ),
        ep("d7", "GET", "/v2/devices/{device_id}/shadow", "Query a device shadow", "devices/show-shadow.rst", "failed"),
      ],
    },
    {
      id: "d_device_groups",
      version: "v2",
      name: "device_groups",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("d8", "GET", "/v2/device-groups", "List device groups", "device-groups/list-device-groups.rst"),
        ep("d9", "POST", "/v2/device-groups", "Create a device group", "device-groups/create-device-group.rst"),
        ep("d10", "GET", "/v2/device-groups/{group_id}", "Query a device group", "device-groups/show-device-group.rst"),
        ep(
          "d11",
          "DELETE",
          "/v2/device-groups/{group_id}",
          "Delete a device group",
          "device-groups/delete-device-group.rst",
        ),
        ep(
          "d12",
          "POST",
          "/v2/device-groups/{group_id}/action",
          "Add or remove devices of a group",
          "device-groups/manage-group-devices.rst",
        ),
      ],
    },
    {
      id: "d_products",
      version: "v2",
      name: "products",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("d13", "GET", "/v2/products", "List products", "products/list-products.rst"),
        ep("d14", "POST", "/v2/products", "Create a product", "products/create-product.rst", "partial"),
        ep("d15", "GET", "/v2/products/{product_id}", "Query a product", "products/show-product.rst"),
        ep("d16", "PUT", "/v2/products/{product_id}", "Update a product", "products/update-product.rst", "partial"),
        ep("d17", "DELETE", "/v2/products/{product_id}", "Delete a product", "products/delete-product.rst"),
      ],
    },
    {
      id: "d_commands",
      version: "v2",
      name: "commands",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep(
          "d18",
          "POST",
          "/v2/devices/{device_id}/commands",
          "Send a command to a device",
          "commands/create-command.rst",
          "failed",
        ),
        ep(
          "d19",
          "POST",
          "/v2/devices/{device_id}/async-commands",
          "Send an asynchronous command",
          "commands/create-async-command.rst",
          "failed",
        ),
        ep(
          "d20",
          "GET",
          "/v2/devices/{device_id}/async-commands",
          "List asynchronous commands",
          "commands/list-async-commands.rst",
          "partial",
        ),
        ep(
          "d21",
          "GET",
          "/v2/devices/{device_id}/async-commands/{command_id}",
          "Query an asynchronous command",
          "commands/show-async-command.rst",
        ),
      ],
    },
    {
      id: "d_upgrades",
      version: "v2",
      name: "upgrades",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("d22", "GET", "/v2/ota-upgrades/packages", "List upgrade packages", "upgrades/list-packages.rst"),
        ep(
          "d23",
          "POST",
          "/v2/ota-upgrades/packages",
          "Upload an upgrade package",
          "upgrades/create-package.rst",
          "partial",
        ),
        ep(
          "d24",
          "GET",
          "/v2/ota-upgrades/packages/{package_id}",
          "Query an upgrade package",
          "upgrades/show-package.rst",
        ),
        ep(
          "d25",
          "DELETE",
          "/v2/ota-upgrades/packages/{package_id}",
          "Delete an upgrade package",
          "upgrades/delete-package.rst",
        ),
        ep("d26", "POST", "/v2/ota-upgrades/tasks", "Create an upgrade task", "upgrades/create-task.rst", "failed"),
      ],
    },
    {
      id: "d_certificates",
      version: "v2",
      name: "certificates",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("d27", "GET", "/v2/certificates", "List CA certificates", "certificates/list-certificates.rst"),
        ep(
          "d28",
          "POST",
          "/v2/certificates",
          "Upload a CA certificate",
          "certificates/create-certificate.rst",
          "partial",
        ),
        ep(
          "d29",
          "GET",
          "/v2/certificates/{certificate_id}",
          "Query a CA certificate",
          "certificates/show-certificate.rst",
        ),
        ep(
          "d30",
          "POST",
          "/v2/certificates/{certificate_id}/action",
          "Verify a CA certificate",
          "certificates/verify-certificate.rst",
          "partial",
        ),
        ep(
          "d31",
          "DELETE",
          "/v2/certificates/{certificate_id}",
          "Delete a CA certificate",
          "certificates/delete-certificate.rst",
        ),
      ],
    },
  ],
  "notifications-hub": [
    {
      id: "n_topics",
      version: "v1",
      name: "topics",
      origin: "auto",
      confirmed: { by: "valeriia", at: "2026-07-29T10:48:00Z" },
      endpoints: [
        ep("n1", "GET", "/v1/notifications/topics", "List topics", "topics/list-topics.rst"),
        ep("n2", "POST", "/v1/notifications/topics", "Create a topic", "topics/create-topic.rst"),
        ep("n3", "DELETE", "/v1/notifications/topics/{topic_urn}", "Delete a topic", "topics/delete-topic.rst"),
      ],
    },
    {
      id: "n_subscriptions",
      version: "v1",
      name: "subscriptions",
      origin: "auto",
      confirmed: null,
      endpoints: [
        ep("n4", "GET", "/v1/notifications/subscriptions", "List subscriptions", "subscriptions/list-subscriptions.rst"),
        ep("n5", "POST", "/v1/notifications/subscriptions", "Subscribe to a topic", "subscriptions/create-subscription.rst"),
      ],
    },
  ],
  "tariff-catalog": [],
};

const src = (service: string, file: string) =>
  `https://github.com/opentelekomcloud-docs/${service}/blob/mockcommit/api-ref/source/${file}`;

interface Placed extends Endpoint {
  /** The resource the scanner put the endpoint in. */
  home: string;
  /** Its place in the scanner's layout of the service. */
  order: number;
}

/** Every endpoint of a service, by id. */
const ENDPOINTS: Record<string, Map<string, Placed>> = Object.fromEntries(
  Object.entries(AUTO).map(([service, resources]) => {
    const placed = resources.flatMap((r) => r.endpoints.map((e) => ({ ...e, home: r.id })));
    return [service, new Map(placed.map((e, order) => [e.id, { ...e, order }]))];
  }),
);

/** A resource as it is laid out now. */
interface Laid {
  id: string;
  version: string;
  name: string;
  origin: GenOrigin;
  /** Endpoint ids, in order. */
  endpoints: string[];
  confirmedBy: string | null;
  confirmedAt: string | null;
}

const laid = (r: LaidOut): Laid => ({
  id: r.id,
  version: r.version,
  name: r.name,
  origin: r.origin,
  endpoints: r.endpoints.map((e) => e.id),
  confirmedBy: r.confirmed?.by ?? null,
  confirmedAt: r.confirmed?.at ?? null,
});

const seed = (): Record<string, Laid[]> =>
  Object.fromEntries(Object.entries(AUTO).map(([service, resources]) => [service, resources.map(laid)]));

const job = (
  id: number,
  status: GenJobStatus,
  pr: number | null,
  started: [by: string, at: string],
  merged: [by: string, at: string] | null = null,
  error: string | null = null,
): GenJob => ({
  id,
  status,
  pr,
  startedBy: started[0],
  startedAt: started[1],
  mergedBy: merged?.[0] ?? null,
  mergedAt: merged?.[1] ?? null,
  error,
});

/** Jobs by target id, then resource id - the prototype's `JOB_SEED`. A resource without one was never generated there. */
const seedJobs = (): Record<string, Record<string, GenJob>> => ({
  python: {
    v1_invoices: job(2088, "done", 131, ["valeriia", "2026-08-11T14:20:00Z"]),
    c_contacts: job(
      2094,
      "failed",
      null,
      ["ivan", "2026-08-12T08:05:00Z"],
      null,
      "LLM backend unavailable — ollama refused the connection after 3 retries",
    ),
    n_topics: job(2071, "merged", 118, ["valeriia", "2026-07-29T11:02:00Z"], ["anna", "2026-08-01T09:40:00Z"]),
    c_customers: job(2079, "merged", 122, ["ivan", "2026-08-04T10:12:00Z"], ["valeriia", "2026-08-06T15:05:00Z"]),
  },
});

/**
 * The pull requests merged on GitHub since the panel last asked, by repository
 * and number, with who merged each and when. The panel learns of a merge only by
 * asking GitHub - on a schedule, which is not simulated here, or when someone
 * refreshes the state (owner decision). The prototype's refresh finds PR 131
 * merged, by its panel user at its "now".
 */
const MERGED_ON_GITHUB: Record<string, { by: string; at: string }> = {
  "opentelekomcloud/python-t-cloud#131": { by: "valeriia", at: "2026-08-12T09:24:00Z" },
};

/** The OTC tenant settings the live calls go out with, keys included - the prototype's. */
const seedSettings = (): OtcSettingsForm => ({
  account: "OTC00000000001000000042",
  tenant: "eu-de_gen-sdk",
  region: "eu-de",
  ak: "AKSTORED9F21",
  sk: "SKSTORED4C7E",
});

/** A type chosen for a field: which, who chose it, and when (ISO 8601). */
interface Choice {
  type: string;
  by: string;
  at: string;
}

const choiceKey = (service: string, resource: string, cls: string, name: string) =>
  JSON.stringify([service, resource, cls, name]);

/**
 * The choices made before: a resource is not generated while a field has a
 * problem nobody decided (owner decision), so the fields of the resources with
 * a job have theirs. The prototype has none; each is the first type offered,
 * chosen by who started the generation, before the prototype's `JOB_SEED` has
 * it start (owner decision).
 */
const seedChoices = () =>
  new Map<string, Choice>([
    [
      choiceKey("billing-api", "v1_invoices", "Invoice", "amount"),
      { type: "Integer", by: "valeriia", at: "2026-08-11T14:12:00Z" },
    ],
    [
      choiceKey("billing-api", "v1_invoices", "Invoice", "items"),
      { type: "List[InvoiceItem]", by: "valeriia", at: "2026-08-11T14:15:00Z" },
    ],
    [
      choiceKey("customer-core", "c_customers", "Customer", "active"),
      { type: "Boolean", by: "ivan", at: "2026-08-04T10:05:00Z" },
    ],
  ]);

/** The layout of every service as it is now: the scanner's, edited. */
let layout = seed();
/** Resources made by hand so far, for their ids. */
let made = 0;
/** The jobs as they are now: the seed, and the generations started since. */
let jobs = seedJobs();
/** The number of the last job started here: they count on from 2101, past the prototype's seed. */
let lastJob = 2100;
/** The types chosen for fields with a problem, by `choiceKey`: the seed, and the choices made and taken back since. */
let choices = seedChoices();
/** Request ids OTC has handed out to live calls so far. */
let calls = 0;
/** The OTC tenant settings as saved. The keys stay here: `otcSettings` says whether each is stored. */
let settings = seedSettings();

/** Back to the seed. Tests share this module's memory, so each one that edits starts here. */
export function resetGenerationMock() {
  layout = seed();
  made = 0;
  jobs = seedJobs();
  lastJob = 2100;
  choices = seedChoices();
  calls = 0;
  settings = seedSettings();
}

const jobsOf = (resource: string): Partial<Record<string, GenJob>> =>
  Object.fromEntries(
    TARGETS.flatMap((t) => {
      const job = jobs[t.id]?.[resource];
      return job ? [[t.id, { ...job }]] : [];
    }),
  );

function summarize(resources: string[], target: string): GenTargetSummary {
  const onTarget = jobs[target] ?? {};
  const count = (status: GenJobStatus) => resources.filter((r) => onTarget[r]?.status === status).length;
  const merged = count("merged");
  const untouched = resources.filter((r) => !onTarget[r]).length;
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

function layoutOf(service: string): Laid[] {
  const resources = layout[service];
  if (!resources) throw new Error(`${service} is not in Generation`);
  return resources;
}

const resourceIds = (name: string) => layoutOf(name).map((r) => r.id);

function resourceOf(service: string, id: string): Laid {
  const r = layoutOf(service).find((x) => x.id === id);
  if (!r) throw new Error(`${service} has no resource ${id}`);
  return r;
}

function endpointOf(service: string, id: string): Placed {
  const endpoint = ENDPOINTS[service]?.get(id);
  if (!endpoint) throw new Error(`${service} has no endpoint ${id}`);
  return endpoint;
}

function endpointView(service: string, id: string): GenEndpoint {
  const { method, uri, title, file, status } = endpointOf(service, id);
  return { id, method, uri, title, src: src(service, file), status };
}

function targetOf(id: string): GenTarget {
  const target = TARGETS.find((t) => t.id === id);
  if (!target) throw new Error(`There is no target ${id}`);
  return target;
}

export function generationTargets(): GenTarget[] {
  return TARGETS.map((t) => ({ ...t }));
}

export function otcSettings(): OtcSettings {
  const { ak, sk, ...rest } = settings;
  return { ...rest, akStored: ak !== "", skStored: sk !== "" };
}

/** The settings the form sends; a key it leaves empty stays as stored. */
export function saveOtcSettings({ ak, sk, ...rest }: OtcSettingsForm) {
  settings = { ...rest, ak: ak || settings.ak, sk: sk || settings.sk };
}

/**
 * A test of the OTC tenant the form names, with the stored keys where it leaves
 * them empty. As in the prototype, it can be called once there are both keys
 * and a tenant; nothing is saved.
 */
export function testOtcSettings({ ak, sk, tenant }: OtcSettingsForm): OtcCheck {
  return { error: (ak || settings.ak) && (sk || settings.sk) && tenant ? null : "AK/SK or tenant missing" };
}

export function generationServices(): GenService[] {
  return Object.keys(layout).map((name) => ({
    name,
    targets: Object.fromEntries(TARGETS.map((t) => [t.id, summarize(resourceIds(name), t.id)])),
  }));
}

/** The layout of one service, in order, with each resource's job on every target. */
export function generationResources(service: string): GenResource[] {
  return layoutOf(service).map((r) => ({
    id: r.id,
    version: r.version,
    name: r.name,
    endpoints: r.endpoints.map((id) => endpointView(service, id)),
    origin: r.origin,
    confirmedBy: r.confirmedBy,
    confirmedAt: r.confirmedAt,
    jobs: jobsOf(r.id),
  }));
}

/** The panel's rules for the shared attention band: resources waiting for review
 *  and resources whose generation failed, over every connected target. */
export function generationAttention(): AttentionRule[] {
  const live = TARGETS.filter((t) => t.live);
  const resources = Object.keys(layout).flatMap(resourceIds);
  const tally = (status: GenJobStatus) =>
    live.reduce((n, t) => n + resources.filter((r) => jobs[t.id]?.[r]?.status === status).length, 0);
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

// --- Layout edits ----------------------------------------------------------

/** Generating, in review, or merged on every connected target: the layout of the resource must not change. */
function frozen(r: Laid): boolean {
  const jobs = jobsOf(r.id);
  return lockingJob(jobs, TARGETS) != null || mergedEverywhere(jobs, TARGETS);
}

/** A resource whose layout may change - or the refusal that says why it may not. */
function editable(service: string, id: string): Laid {
  const r = resourceOf(service, id);
  if (frozen(r)) throw new Error(`The layout of ${r.name} is frozen: it is generating, in review or merged`);
  return r;
}

const fromScanner = (service: string, id: string) => AUTO[service]?.find((r) => r.id === id);

/** A new name; the page has checked it. It does not confirm the resource (owner decision). */
export function renameResource(service: string, id: string, name: string) {
  editable(service, id).name = name;
}

/** An endpoint to the end of another resource, in this version or another, as in the prototype. */
export function moveEndpoint(service: string, endpoint: string, to: string) {
  const from = layoutOf(service).find((r) => r.endpoints.includes(endpoint));
  if (!from) throw new Error(`${service} has no endpoint ${endpoint}`);
  const into = editable(service, to);
  if (from === into) return;
  editable(service, from.id);
  from.endpoints = from.endpoints.filter((e) => e !== endpoint);
  into.endpoints.push(endpoint);
}

/**
 * An empty resource made by hand, after the last one of its version. It is not
 * confirmed - confirming takes the button (owner decision), where the prototype
 * made it confirmed - so it is `new` until someone does.
 */
export function addResource(service: string, version: string) {
  const resources = layoutOf(service);
  const last = resources.findLastIndex((r) => r.version === version);
  if (last < 0) throw new Error(`${service} has no version ${version}`);
  const taken = new Set(resources.filter((r) => r.version === version).map((r) => r.name));
  let n = 1;
  while (taken.has(`new_resource_${n}`)) n++;
  resources.splice(last + 1, 0, {
    id: `new_${version}_${++made}`,
    version,
    name: `new_resource_${n}`,
    origin: "new",
    endpoints: [],
    confirmedBy: null,
    confirmedAt: null,
  });
}

/** The confirmation, with who gives it and when (owner decision). */
export function confirmResource(service: string, id: string, by: string) {
  const r = editable(service, id);
  if (!by) throw new Error("A confirmation has to record who gives it");
  if (r.confirmedBy != null) throw new Error(`${r.name} is already confirmed by ${r.confirmedBy}`);
  r.confirmedBy = by;
  r.confirmedAt = new Date().toISOString();
}

/**
 * Put the scanner's layout back on `reset`: each resource gets its name, its
 * endpoints and its confirmation as the scanner's layout has them - the
 * prototype restores a resource from `AUTO_STRUCTURE` whole. An endpoint is only
 * ever moved, never dropped: one that sits in a reset resource but belongs
 * elsewhere goes back to where the scanner put it. A frozen resource neither
 * gives nor takes, so what it holds stays where it is.
 */
function putBack(service: string, reset: Laid[]) {
  const resources = layoutOf(service);
  const resetting = new Set(reset);
  const byId = new Map(resources.map((r) => [r.id, r]));
  const placed = resources.flatMap((holder) => holder.endpoints.map((id) => ({ id, holder })));
  for (const { id, holder } of placed) {
    /* the scanner's resources are never removed, so an endpoint's home is always there */
    const home = byId.get(endpointOf(service, id).home) as Laid;
    if (home === holder || !(resetting.has(home) || resetting.has(holder)) || frozen(home) || frozen(holder)) continue;
    holder.endpoints = holder.endpoints.filter((e) => e !== id);
    home.endpoints.push(id);
  }
  for (const r of reset) {
    const auto = fromScanner(service, r.id);
    if (!auto) continue;
    r.name = auto.name;
    r.confirmedBy = auto.confirmed?.by ?? null;
    r.confirmedAt = auto.confirmed?.at ?? null;
    r.endpoints.sort((a, b) => endpointOf(service, a).order - endpointOf(service, b).order);
  }
}

/** One resource back to the scanner's layout. One made by hand is not in it, so
 *  nothing changes there, as in the prototype. */
export function resetResource(service: string, id: string) {
  const r = editable(service, id);
  if (fromScanner(service, id)) putBack(service, [r]);
}

/**
 * A version back to the scanner's layout, but for its frozen resources. The
 * resources made by hand in it go, as in the prototype - each once nothing is
 * left in it: an endpoint that could not go home stays, and so does a resource
 * that has a job.
 */
export function resetVersion(service: string, version: string) {
  const resources = layoutOf(service);
  const inVersion = resources.filter((r) => r.version === version);
  if (!inVersion.length) throw new Error(`${service} has no version ${version}`);
  putBack(
    service,
    inVersion.filter((r) => !frozen(r)),
  );
  layout[service] = resources.filter(
    (r) =>
      r.version !== version ||
      fromScanner(service, r.id) != null ||
      r.endpoints.length > 0 ||
      Object.keys(jobsOf(r.id)).length > 0,
  );
}

// --- Generation spec -------------------------------------------------------

interface FieldIssue {
  problem: GenFieldProblem;
  text: string;
  /** The types to choose from, each with where it comes from. */
  options: [type: string, note: string][];
  /** The documents that describe the field, by path under `api-ref/source`. */
  docs: string[];
}

interface Field {
  name: string;
  type: string;
  required: boolean;
  description: string;
  issue?: FieldIssue;
}

interface Class {
  name: string;
  fields: Field[];
}

const field = (name: string, type: string, required: boolean, description: string, issue?: FieldIssue): Field => ({
  name,
  type,
  required,
  description,
  issue,
});

/** The classes the generator would emit, by resource id - the prototype's `ENTITIES`. */
const ENTITIES: Record<string, Class[]> = {
  v1_invoices: [
    {
      name: "Invoice",
      fields: [
        field("id", "String", true, "Invoice ID"),
        field("project_id", "String", true, "Owning project"),
        field("amount", "Integer", true, "Total amount, minor units", {
          problem: "type_conflict",
          text: "Conflict: the create page documents this field as String, the get page as Integer. Pick the type the SDK should use before generating.",
          options: [
            ["Integer", "as in show-invoice.rst"],
            ["String", "as in create-invoice.rst"],
          ],
          docs: ["invoices/create-invoice.rst", "invoices/show-invoice.rst"],
        }),
        field("items", "Unknown", false, "Invoice line items", {
          problem: "unknown_type",
          text: "Type not recognized — the doc writes “List<x>”. The generator needs a concrete element type for the list.",
          options: [
            ["List[InvoiceItem]", "element fields match InvoiceItem"],
            ["List[String]", "treat items as opaque ids"],
            ["String", "keep the raw value"],
          ],
          docs: ["invoices/show-invoice.rst"],
        }),
        field("created_at", "DateTime", false, "Creation timestamp"),
      ],
    },
    {
      name: "InvoiceItem",
      fields: [
        field("resource_id", "String", true, "Billed resource"),
        field("quantity", "Integer", true, "Billed quantity"),
        field("unit_price", "Integer", false, "Price per unit, minor units"),
      ],
    },
  ],
  v1_payments: [
    {
      name: "Payment",
      fields: [
        field("id", "String", true, "Payment ID"),
        field("invoice_id", "String", true, "Invoice this payment settles"),
        field("method", "Unknown", true, "Payment method", {
          problem: "unknown_type",
          text: "Type not recognized — the table cell reads “enum (see below)” and the values are only in prose. Choose an enum or a plain string.",
          options: [
            ["Enum[PaymentMethod]", "values listed in the prose below the table"],
            ["String", "accept any value"],
          ],
          docs: ["payments/create-payment.rst"],
        }),
        field("paid_at", "DateTime", false, "Settlement timestamp"),
      ],
    },
  ],
  c_customers: [
    {
      name: "Customer",
      fields: [
        field("id", "String", true, "Customer ID"),
        field("name", "String", true, "Legal name"),
        field("segment", "String", false, "Sales segment"),
        field("active", "Boolean", false, "Whether the account is active", {
          problem: "type_conflict",
          text: "Conflict: the list page documents this field as String (“true”/“false”), the update page as Boolean.",
          options: [
            ["Boolean", "as in update-customer.rst"],
            ["String", "as in list-customers.rst"],
          ],
          docs: ["customers/list-customers.rst", "customers/update-customer.rst"],
        }),
      ],
    },
  ],
};

const singular = (n: string) => (n.endsWith("ses") ? n.slice(0, -2) : n.endsWith("s") ? n.slice(0, -1) : n);
const pascal = (n: string) =>
  n
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join("");

/** The classes of a resource, or - with none prepared, as in the prototype - one named after it. */
const classesOf = (id: string, name: string): Class[] =>
  ENTITIES[id] ?? [
    {
      name: pascal(singular(name)),
      fields: [
        field("id", "String", true, "Resource ID"),
        field("name", "String", false, "Human-readable name"),
        field("created_at", "DateTime", false, "Creation timestamp"),
      ],
    },
  ];

/** A POST to one of these on a collection is a custom action, not a create - the prototype's list. */
const ACTIONS = new Set(["export", "action", "batch", "validate"]);

/**
 * A base CRUD method, guessed from the HTTP method and the shape of the URI as
 * the prototype's `classifyOp` does; anything else is a custom action named
 * after the last literal segment of the URI (its `customName`).
 */
function operationOf({ method, uri }: GenEndpoint): Pick<GenOperation, "kind" | "sdkMethod"> {
  const segs = uri.split("/").filter(Boolean);
  const last = segs.at(-1) ?? "";
  const onItem = last.startsWith("{");
  const collectionAction = segs.length >= 2 && !segs[segs.length - 2].startsWith("{") && ACTIONS.has(last);
  const base =
    method === "GET"
      ? onItem
        ? "get"
        : "list"
      : method === "POST"
        ? onItem || collectionAction
          ? null
          : "create"
        : method === "PUT" || method === "PATCH"
          ? onItem
            ? "update"
            : null
          : method === "DELETE" && onItem
            ? "delete"
            : null;
  if (base) return { kind: "base", sdkMethod: base };
  const named = segs.filter((s) => !s.startsWith("{"));
  return { kind: "custom", sdkMethod: (named.at(-1) ?? "action").replace(/-/g, "_") };
}

/** The query parameters every base list and get takes - the prototype's `QUERY_IR`. */
const QUERY: Partial<Record<string, Field[]>> = {
  list: [
    field("limit", "Integer", false, "Number of records returned"),
    field("marker", "String", false, "Pagination marker of the last record"),
    field("sort_key", "String", false, "Field the result is sorted by"),
  ],
  get: [field("fields", "String", false, "Comma-separated list of fields to return")],
};

/** The ones a document adds, by endpoint id - the prototype's `QUERY_EXTRA`, which has them by resource. */
const QUERY_EXTRA: Record<string, Field[]> = {
  e1: [field("status", "String", false, "Filter by invoice status")],
  e5: [field("invoice_id", "String", false, "Only payments of this invoice")],
  c1: [field("segment", "String", false, "Filter by sales segment")],
};

/** The query parameters of an operation. */
const queryOf = (endpoint: GenEndpoint, { kind, sdkMethod }: Pick<GenOperation, "kind" | "sdkMethod">) =>
  [...((kind === "base" && QUERY[sdkMethod]) || []), ...(QUERY_EXTRA[endpoint.id] ?? [])].map(
    ({ name, type, required, description }) => ({ name, type, required, description }),
  );

/** Fields of the resource whose problem nobody has decided yet. */
const undecided = (service: string, r: Laid) =>
  classesOf(r.id, r.name).reduce(
    (n, c) => n + c.fields.filter((f) => f.issue && !choices.has(choiceKey(service, r.id, c.name, f.name))).length,
    0,
  );

/** What a resource will be generated as: an operation per endpoint, in order, and its classes with the types chosen so far. */
export function generationSpec(service: string, id: string): GenSpec {
  const r = resourceOf(service, id);
  return {
    operations: r.endpoints.map((id) => {
      const endpoint = endpointView(service, id);
      const operation = operationOf(endpoint);
      return { endpoint, ...operation, query: queryOf(endpoint, operation) };
    }),
    classes: classesOf(r.id, r.name).map((c) => ({
      name: c.name,
      fields: c.fields.map(({ name, type, required, description, issue }) => {
        const choice = choices.get(choiceKey(service, r.id, c.name, name));
        return {
          name,
          type,
          required,
          description,
          issue: issue
            ? {
                problem: issue.problem,
                text: issue.text,
                options: issue.options.map(([option, note]) => ({ type: option, note })),
                docs: issue.docs.map((file) => ({ label: file.split("/").at(-1) ?? file, src: src(service, file) })),
                choice: choice ? { ...choice } : null,
              }
            : null,
        };
      }),
    })),
  };
}

/** The type for a field with a problem, recorded with who chooses it and when; `type` null takes the choice back. */
export function chooseType(service: string, id: string, cls: string, name: string, type: string | null, by: string) {
  const r = resourceOf(service, id);
  const issue = classesOf(r.id, r.name)
    .find((c) => c.name === cls)
    ?.fields.find((f) => f.name === name)?.issue;
  if (!issue) throw new Error(`${cls}.${name} of ${r.name} has nothing to decide`);
  const key = choiceKey(service, r.id, cls, name);
  if (type == null) {
    choices.delete(key);
    return;
  }
  if (!by) throw new Error("A choice has to record who makes it");
  if (!issue.options.some(([option]) => option === type)) throw new Error(`${type} is not an option for ${cls}.${name}`);
  choices.set(key, { type, by, at: new Date().toISOString() });
}

const JOB_REFUSAL: Record<Exclude<GenJobStatus, "failed">, string> = {
  running: "is generating",
  done: "is in review",
  merged: "is merged",
};

const holdRefusal = (hold: Hold, target: GenTarget): string => {
  switch (hold.reason) {
    case "confirm":
      return "its layout is not confirmed";
    case "empty":
      return "it has no endpoints";
    case "notOk":
      return `${hold.n} of its endpoints are not recognized in full`;
    case "waitsOn":
      return `it is not merged in ${hold.base} yet`;
    case "notConnected":
      return `${target.label} is not connected`;
  }
};

/**
 * A generation job for the resource on the target, as the prototype's
 * `startGeneration` starts it: numbered, running, no pull request yet, with who
 * started it and when. Refused while a field still has a problem nobody decided
 * (owner decision), whenever the resource's card would not offer Generate there,
 * and over a job that has not failed - one generating, in review or merged is
 * not replaced.
 */
export function startGeneration(service: string, id: string, targetId: string, by: string) {
  const resource = generationResources(service).find((r) => r.id === id);
  if (!resource) throw new Error(`${service} has no resource ${id}`);
  const target = targetOf(targetId);
  const current = resource.jobs[target.id];
  if (current && current.status !== "failed") {
    throw new Error(`${resource.name} ${JOB_REFUSAL[current.status]} on ${target.label}`);
  }
  const hold = holdOf(resource, target, TARGETS);
  if (hold) throw new Error(`${resource.name} cannot be generated for ${target.label}: ${holdRefusal(hold, target)}`);
  const open = undecided(service, resourceOf(service, id));
  if (open) throw new Error(`${resource.name} cannot be generated: ${open} field(s) still to decide`);
  if (!by) throw new Error("A generation has to record who starts it");
  (jobs[target.id] ??= {})[id] = job(++lastJob, "running", null, [by, new Date().toISOString()]);
}

/** The resource, and its job on the target, which must have opened a pull request by now. */
function withPullRequest(service: string, id: string, target: GenTarget): { resource: Laid; job: GenJob } {
  const resource = resourceOf(service, id);
  const current = jobs[target.id]?.[id];
  if (current?.pr == null) throw new Error(`${resource.name} has no pull request on ${target.label}`);
  return { resource, job: current };
}

/**
 * The state of the job's pull request, from GitHub (owner decision): a merge
 * made there since the panel last asked is taken over, with who merged it and
 * when. A pull request still open there leaves the job as it is.
 */
export function refreshPullRequest(service: string, id: string, targetId: string) {
  const target = targetOf(targetId);
  const { job: current } = withPullRequest(service, id, target);
  const merge = MERGED_ON_GITHUB[`${target.repo}#${current.pr}`];
  if (!merge || current.status === "merged") return;
  current.status = "merged";
  current.mergedBy = merge.by;
  current.mergedAt = merge.at;
}

/** A value of the kind the docs give a field, for the sample an answer is made of - the prototype's `sampleFor`. */
const sampleValue = (resource: string, { name, type }: Field) =>
  name === "id"
    ? `${singular(resource)}-3f9c`
    : type === "Integer"
      ? 1200
      : type === "Boolean"
        ? true
        : type === "DateTime"
          ? "2026-08-12T08:41:07Z"
          : `${name}-value`;

/**
 * A live call of one of the resource's operations, through the SDK generated in
 * the job's pull request, as the prototype's `sendLive` answers it: an empty
 * path parameter has the SDK call the collection URL, which OTC does not find;
 * otherwise OTC answers with the resource's first class. Only a GET is called
 * (owner decision) - nothing is created in the tenant, so there is nothing to
 * clean up. The query parameters go out with the call; as in the prototype,
 * they change nothing in the answer.
 */
export function liveCall(
  service: string,
  id: string,
  targetId: string,
  endpointId: string,
  request: { path: Record<string, string>; query: Record<string, string> },
): GenLiveResponse {
  const { resource: r } = withPullRequest(service, id, targetOf(targetId));
  if (!r.endpoints.includes(endpointId)) throw new Error(`${r.name} has no endpoint ${endpointId}`);
  const endpoint = endpointView(service, endpointId);
  if (endpoint.method !== "GET") {
    throw new Error(`Only GET operations are called live, not ${endpoint.method} ${endpoint.uri}`);
  }
  const missing = pathParams(endpoint.uri).find((p) => !request.path[p]?.trim());
  if (missing) {
    const requestId = `req-${++calls}f3a91`;
    return {
      code: 404,
      reason: "Not Found",
      ms: 240,
      requestId,
      body: { error_code: "APIGW.0301", error_msg: "resource not found", request_id: requestId },
      error: {
        message: "Resource not found",
        hint: `The path parameter ${missing} is empty, so the SDK called the collection URL with a trailing slash. Fill it in with a real id.`,
      },
    };
  }
  const [cls] = classesOf(r.id, r.name);
  const item = Object.fromEntries(cls.fields.map((f) => [f.name, sampleValue(r.name, f)]));
  return {
    code: 200,
    reason: "OK",
    ms: 480,
    requestId: null,
    body: operationOf(endpoint).sdkMethod === "list" ? { [r.name]: [item], count: 1 } : { [singular(r.name)]: item },
    error: null,
  };
}
