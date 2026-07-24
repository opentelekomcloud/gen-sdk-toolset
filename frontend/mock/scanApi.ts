/**
 * DEV-ONLY mock for /api/scan/* — the backend does not serve these routes yet
 * (scan_router is still commented out in src/tools/panel/api/app.py).
 * Enable with MOCK_API=1. DELETE this file once the real routes land.
 *
 * Shapes mirror src/features/scan/api/types.local.ts, which in turn mirrors
 * the persistence models (service / job / generation / document): full
 * commit_hash, created_at as scan timestamp, completeness as 0..1 float,
 * ok/partial/failed/unsupported counts, nullable active/latest ids.
 */
import type { Connect, Plugin } from "vite";

type SectionCounts = { ok?: number; partial?: number; failed?: number; skipped?: number; missing?: number };
type Doc = {
  id: number; method: string | null; uri: string | null; title: string | null;
  path: string; overall_status: string; issues: { code: string; count: number }[];
};
type Gen = {
  id: number; source_job_id: number; branch: string; commit_hash: string;
  scanner_version: string; document_schema_version: string; incomplete_reason: string | null;
  documents_total: number; endpoints_total: number; non_endpoint_documents: number; issues_total: number;
  ok_count: number; partial_count: number; failed_count: number; unsupported_count: number;
  completeness: number | null; created_at: string;
  /** mock-only: service-level view fields applied when this gen becomes active */
  view: Record<string, unknown>;
};

const SECTIONS = ["path_params", "query_params", "headers", "body", "response", "example_request", "example_response"];
const V = "3.2.0";
const SCHEMA_V = "1.4";
const NOW = "2026-07-23T09:15:00Z";
const HASH = (seed: string) =>
  Array.from({ length: 40 }, (_, i) => "0123456789abcdef"[(seed.charCodeAt(i % seed.length) * (i + 3)) % 16]).join("");

const rollup = (ok: number, partial = 0, failed = 0, skipped = 0, missing = 0) =>
  Object.fromEntries(SECTIONS.map((s) => [s, { ok, partial, failed, skipped, missing } as SectionCounts]));

type MockService = {
  name: string; scan_status: string; documents: number | null; struct_ok: number | null;
  scanner_version: string | null; scanned_at: string | null; docs_changed: boolean;
  rescan_reason: string | null; error: string | null;
  job_id?: number; initiated_by?: string | null; started_at?: string;
  [k: string]: unknown;
};

const svc = (o: Partial<MockService> & { name: string; scan_status: string }): MockService => ({
  scanner_version: V, scanned_at: NOW, docs_changed: false, rescan_reason: null, error: null,
  overall_breakdown: {}, section_rollup: rollup(0), struct_ok: null, documents: null,
  top_issues: [], non_endpoint_documents: 0, head_commit: null, interruption: null,
  active_generation: null, latest_generation: null, ...o,
});

const SERVICES = [
  svc({ name: "billing-api", scan_status: "scanned", documents: 42, struct_ok: 97,
    overall_breakdown: { ok: 40, partial: 2 }, section_rollup: rollup(40, 2),
    top_issues: [{ code: "missing_example", count: 3 }] }),
  svc({ name: "customer-core", scan_status: "scanned", documents: 128, struct_ok: 88, scanner_version: "3.1.0",
    rescan_reason: "version", overall_breakdown: { ok: 110, partial: 12, unsupported: 6 },
    section_rollup: rollup(110, 12, 0, 6),
    top_issues: [{ code: "unknown_type", count: 14 }, { code: "missing_description", count: 9 }] }),
  svc({ name: "device-mgmt", scan_status: "partial", documents: 31, struct_ok: 64, rescan_reason: "partial",
    overall_breakdown: { ok: 18, partial: 9, failed: 4 }, section_rollup: rollup(18, 9, 4),
    top_issues: [{ code: "table_parse_error", count: 6 }] }),
  svc({ name: "legacy-soap-bridge", scan_status: "failed", rescan_reason: "retry",
    error: "clone failed: repository archived (HTTP 403)", scanned_at: null, scanner_version: null,
    interruption: { kind: "permission_denied", repository: "legacy-soap-bridge",
      message: "clone failed: repository archived (HTTP 403)", reset_time: null } }),
  svc({ name: "notifications-hub", scan_status: "scanned", documents: 17, struct_ok: 94, docs_changed: true,
    rescan_reason: "drift", overall_breakdown: { ok: 16, partial: 1 }, section_rollup: rollup(16, 1) }),
  svc({ name: "payments-gw", scan_status: "scanning", documents: 55, struct_ok: 91,
    overall_breakdown: { ok: 50, partial: 5 }, section_rollup: rollup(50, 5),
    job_id: 1042, initiated_by: "valeriia", started_at: "2026-07-23T12:58:00Z" }),
  svc({ name: "tariff-catalog", scan_status: "scanned", documents: 0, non_endpoint_documents: 7 }),
  svc({ name: "roaming-info", scan_status: "not_scanned", scanned_at: null, scanner_version: null }),
];

/* ---------- G1: generation history (newest first) + active pointer ---------- */
const GENS: Record<string, Gen[]> = {};
const ACTIVE: Record<string, number> = {};
let genId = 500;
let jobId = 900;

const mkGen = (name: string, s: MockService, at: string, ver: string, delta: { docs?: number; ok?: number; partial?: number; failed?: number; unsupported?: number; struct?: number; incomplete?: string | null } = {}): Gen => {
  const ob = { ...(s.overall_breakdown as Record<string, number>) };
  const docs = (s.documents as number) + (delta.docs ?? 0);
  const ok = (ob.ok ?? 0) + (delta.ok ?? 0);
  const partial = (ob.partial ?? 0) + (delta.partial ?? 0);
  const failed = (ob.failed ?? 0) + (delta.failed ?? 0);
  const unsupported = (ob.unsupported ?? 0) + (delta.unsupported ?? 0);
  const struct = (s.struct_ok as number) + (delta.struct ?? 0);
  const breakdown = { ...(ok && { ok }), ...(partial && { partial }), ...(failed && { failed }), ...(unsupported && { unsupported }) };
  return {
    id: ++genId, source_job_id: ++jobId, branch: "main", commit_hash: HASH(name + at),
    scanner_version: ver, document_schema_version: SCHEMA_V, incomplete_reason: delta.incomplete ?? null,
    documents_total: docs, endpoints_total: docs, non_endpoint_documents: 0,
    issues_total: partial * 2 + failed * 3, ok_count: ok, partial_count: partial,
    failed_count: failed, unsupported_count: unsupported,
    completeness: struct / 100, created_at: at,
    view: { documents: docs, struct_ok: struct, overall_breakdown: breakdown,
      section_rollup: rollup(ok, partial, failed, unsupported), scanned_at: at, scanner_version: ver },
  };
};

for (const s of SERVICES) {
  if (s.documents == null || s.error || s.scan_status === "not_scanned" || s.documents === 0) continue;
  const history: Gen[] = [];
  /* older generations first so ids ascend, then reverse to newest-first */
  if (s.name === "customer-core")
    history.push(mkGen(s.name, s, "2026-05-02T08:40:00Z", "3.0.2", { docs: -9, ok: -8, partial: -1, struct: -6, incomplete: "rate limited after 119 documents" }));
  if (["billing-api", "customer-core", "device-mgmt", "notifications-hub", "payments-gw"].includes(s.name))
    history.push(mkGen(s.name, s, "2026-06-18T14:20:00Z", "3.1.0", { docs: -3, ok: -4, partial: 1, struct: -4 }));
  history.push(mkGen(s.name, s, (s.scanned_at as string) ?? NOW, (s.scanner_version as string) ?? V));
  history.reverse();
  GENS[s.name as string] = history;
  ACTIVE[s.name as string] = history[0].id;
  s.head_commit = s.docs_changed ? HASH(s.name + "drifted") : history[0].commit_hash;
}

/* strip the mock-only `view` payload before a Gen goes over the wire */
const pub = (g: Gen): Omit<Gen, "view"> => {
  const rest: Partial<Gen> = { ...g };
  delete rest.view;
  return rest as Omit<Gen, "view">;
};
const applyActive = (s: MockService) => {
  const history = GENS[s.name as string];
  if (!history) return s;
  const active = history.find((g) => g.id === ACTIVE[s.name as string]) ?? history[0];
  return { ...s, ...active.view, active_generation: pub(active), latest_generation: pub(history[0]) };
};

const DOCS: Record<string, Doc[]> = {};
let docId = 10000;
for (const s of SERVICES) {
  const n = (s.documents as number) ?? 0;
  DOCS[s.name as string] = Array.from({ length: n }, (_, i) => {
    const status = i % 13 === 5 ? "failed" : i % 7 === 3 ? "partial" : i % 17 === 9 ? "unsupported" : "ok";
    return {
      id: ++docId,
      method: ["GET", "POST", "PUT", "DELETE", "PATCH"][i % 5],
      uri: `/v2/${s.name}/resource-${i + 1}`,
      title: `Operation ${i + 1} of ${s.name}`,
      path: `api-ref/source/ops/operation-${i + 1}.md`,
      overall_status: status,
      issues: status === "ok" ? [] : [{ code: status === "failed" ? "table_parse_error" : "unknown_type", count: (i % 3) + 1 }],
    };
  }).sort((a, b) => "failed,partial,unsupported,ok".indexOf(a.overall_status) - "failed,partial,unsupported,ok".indexOf(b.overall_status));
}
/* documents served from the ACTIVE generation: older gens expose a truncated list */
const docsForActive = (name: string): Doc[] => {
  const history = GENS[name];
  const all = DOCS[name] ?? [];
  if (!history) return all;
  const active = history.find((g) => g.id === ACTIVE[name]) ?? history[0];
  return all.slice(0, active.documents_total);
};

const detail = (name: string, id: number) => ({
  id, method: "POST", uri: `/v2/${name}/items`, title: `Detail of ${id}`, api_version: "2.4", overall_status: "partial",
  failure_reason: null,
  sections: SECTIONS.map((sec, i) => ({
    name: sec, status: i === 3 ? "partial" : i === 5 ? "skipped" : "ok",
    fields_total: 6, fields_recognized: i === 3 ? 4 : 6, fields_unknown_type: i === 3 ? 2 : 0,
    parameters: sec.startsWith("example") ? null : [
      { name: "customerId", param_type: "string", mandatory: true, description: "Unique customer identifier" },
      { name: "options", param_type: "object", mandatory: false, description: "Request options", children: [
        { name: "locale", param_type: "string", mandatory: false, description: "BCP-47 locale" },
        { name: "flags", param_type: i === 3 ? "Unknown" : "array[string]", mandatory: false, description: "" },
      ]},
    ],
    issues: i === 3 ? [{ code: "unknown_type", location: "options.flags", details: "cannot map cell 'bitmask?'" }] : [],
  })),
});

const EXCLUDED = [{ name: "internal-sandbox", reason: "Test repository, never had real docs", excluded_by: "ivan", excluded_at: "2026-06-30" }];

export function mockScanApi(): Plugin {
  const json = (res: Parameters<Connect.NextHandleFunction>[1], body: unknown, status = 200) => {
    res.statusCode = status;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify(body));
  };
  return {
    name: "mock-scan-api",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = new URL(req.url ?? "/", "http://x");
        if (!url.pathname.startsWith("/api/scan")) return next();
        const p = url.pathname.replace("/api/scan", "");
        const q = (url.searchParams.get("q") ?? "").toLowerCase();

        if (p === "/summary") return json(res, {
          scanner_version: V, last_scanned_at: NOW, services_total: SERVICES.length,
          failed_services: SERVICES.filter((s) => s.scan_status === "failed").length,
          documents_total: SERVICES.reduce((a, s) => a + ((s.documents as number) ?? 0), 0),
          scans_running: SERVICES.filter((s) => s.scan_status === "scanning").length,
        });

        if (p === "/attention") return json(res, [
          { code: "failed", panel: "scan", label: "failed and hold no data", count: 1 },
          { code: "version", panel: "scan", label: "scanned with an outdated scanner", count: 1 },
          { code: "drift", panel: "scan", label: "docs changed since last scan", count: 1 },
          { code: "new", panel: "scan", label: "discovered, never scanned", count: 1 },
        ]);

        if (p === "/excluded") return json(res, EXCLUDED);

        if (p === "/services") {
          const status = url.searchParams.get("status") ?? "all";
          const rule = url.searchParams.get("rule");
          const sort = url.searchParams.get("sort") ?? "quality";
          let items = SERVICES.filter((s) => (s.name as string).includes(q)).map(applyActive);
          const counts = Object.fromEntries(
            ["all", "scanned", "partial", "failed", "not_scanned", "scanning", "needs_rescan"].map((k) => [
              k, items.filter((s) => k === "all" || (k === "needs_rescan" ? s.rescan_reason != null : s.scan_status === k)).length,
            ]),
          );
          if (rule) items = items.filter((s) =>
            rule === "failed" ? s.scan_status === "failed"
            : rule === "version" ? s.scanner_version != null && s.scanner_version !== V
            : rule === "drift" ? s.docs_changed
            : s.scan_status === "not_scanned");
          else if (status !== "all") items = items.filter((s) =>
            status === "needs_rescan" ? s.rescan_reason != null : s.scan_status === status);
          items = [...items].sort((a, b) =>
            sort === "name" ? (a.name as string).localeCompare(b.name as string)
            : sort === "docs" ? ((b.documents as number) ?? -1) - ((a.documents as number) ?? -1)
            : ((a.struct_ok as number) ?? 101) - ((b.struct_ok as number) ?? 101));
          return json(res, { items, counts });
        }

        const m = p.match(/^\/services\/([^/]+)(\/.*)?$/);
        if (m) {
          const name = decodeURIComponent(m[1]);
          const rest = m[2] ?? "";
          const service = SERVICES.find((s) => s.name === name);
          if (!service) return json(res, { error: { code: "not_found", message: `service ${name} not found` } }, 404);

          if (rest === "" && req.method === "GET") return json(res, applyActive(service));

          /* G1: generation history + activation */
          if (rest === "/generations") {
            const history = GENS[name] ?? [];
            return json(res, {
              items: history.map(pub),
              active_id: ACTIVE[name] ?? null,
              latest_id: history[0]?.id ?? null,
            });
          }
          const am = rest.match(/^\/generations\/(\d+)\/activate$/);
          if (am && req.method === "POST") {
            const history = GENS[name] ?? [];
            const g = history.find((x) => x.id === Number(am[1]));
            if (!g) return json(res, { error: { code: "not_found", message: `generation ${am[1]} not found` } }, 404);
            if (service.scan_status === "scanning")
              return json(res, { error: { code: "conflict", message: "a scan job is running" } }, 409);
            ACTIVE[name] = g.id;
            /* drift is relative to the ACTIVE generation's commit */
            service.docs_changed = service.head_commit != null && service.head_commit !== g.commit_hash;
            return json(res, { items: history.map(pub), active_id: g.id, latest_id: history[0].id });
          }

          if (rest === "/documents") {
            const status = url.searchParams.get("status");
            const page = Number(url.searchParams.get("page") ?? 1);
            const page_size = 15;
            const all = docsForActive(name).filter((d) => (d.title ?? "").toLowerCase().includes(q) || d.uri?.toLowerCase().includes(q));
            const doc_counts = Object.fromEntries(
              ["all", "ok", "partial", "failed", "unsupported"].map((k) => [k, k === "all" ? all.length : all.filter((d) => d.overall_status === k).length]),
            );
            const filtered = status ? all.filter((d) => d.overall_status === status) : all;
            return json(res, { items: filtered.slice((page - 1) * page_size, page * page_size), total: filtered.length, page, page_size, doc_counts });
          }
          const dm = rest.match(/^\/documents\/(\d+)$/);
          if (dm) return json(res, detail(name, Number(dm[1])));
          if (rest === "/rescan") return json(res, { job_id: 1043 + Math.floor(Math.random() * 100) });
          if (rest === "/exclude" || rest === "/include") { res.statusCode = 204; return res.end(); }
        }
        return json(res, { error: { code: "not_found", message: `no mock for ${url.pathname}` } }, 404);
      });
    },
  };
}
