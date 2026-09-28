/**
 * In-memory stand-in for the Generation backend, which does not exist yet. The
 * hooks in `queries.ts` and `mutations.ts` read and change it; nothing else may,
 * except a test putting it back with `resetGenerationMock`. Data is the
 * prototype's (`TARGETS`, `AUTO_STRUCTURE`, `JOB_SEED`, `CONFIRM_SEED`); service
 * names are those of `mock/scanApi.ts`.
 */
import type { AttentionRule } from "../../../shared/api/types";
import type { DocStatus } from "../../scan/types";
import { lockingJob, mergedEverywhere } from "../lib/layout";
import type {
  GenAttentionCode,
  GenJob,
  GenJobStatus,
  GenOrigin,
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
      confirmed: null,
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

/** The layout of every service as it is now: the scanner's, edited. */
let layout = seed();
/** Resources made by hand so far, for their ids. */
let made = 0;

/** Back to the seed. Tests share this module's memory, so each one that edits starts here. */
export function resetGenerationMock() {
  layout = seed();
  made = 0;
}

/** Jobs by target id, then resource id. A resource without one was never generated there. */
const JOBS: Record<string, Record<string, GenJob>> = {
  python: {
    v1_invoices: { status: "done", pr: 131 },
    c_contacts: { status: "failed", pr: null },
    n_topics: { status: "merged", pr: 118 },
    c_customers: { status: "merged", pr: 122 },
  },
};

const jobsOf = (resource: string): Partial<Record<string, GenJob>> =>
  Object.fromEntries(
    TARGETS.flatMap((t) => {
      const job = JOBS[t.id]?.[resource];
      return job ? [[t.id, { ...job }]] : [];
    }),
  );

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

function layoutOf(service: string): Laid[] {
  const resources = layout[service];
  if (!resources) throw new Error(`${service} is not in Generation`);
  return resources;
}

const resourceIds = (name: string) => layoutOf(name).map((r) => r.id);

function endpointOf(service: string, id: string): Placed {
  const endpoint = ENDPOINTS[service]?.get(id);
  if (!endpoint) throw new Error(`${service} has no endpoint ${id}`);
  return endpoint;
}

export function generationTargets(): GenTarget[] {
  return TARGETS.map((t) => ({ ...t }));
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
    endpoints: r.endpoints.map((id) => {
      const { method, uri, title, file, status } = endpointOf(service, id);
      return { id, method, uri, title, src: src(service, file), status };
    }),
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

// --- Layout edits ----------------------------------------------------------

/** Generating, in review, or merged on every connected target: the layout of the resource must not change. */
function frozen(r: Laid): boolean {
  const jobs = jobsOf(r.id);
  return lockingJob(jobs, TARGETS) != null || mergedEverywhere(jobs, TARGETS);
}

/** A resource whose layout may change - or the refusal that says why it may not. */
function editable(service: string, id: string): Laid {
  const r = layoutOf(service).find((x) => x.id === id);
  if (!r) throw new Error(`${service} has no resource ${id}`);
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
