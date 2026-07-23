/**
 * DEV-ONLY mock for /api/scan/* — the backend does not serve these routes yet
 * (scan_router is still commented out in src/tools/panel/api/app.py).
 * Enable with MOCK_API=1. DELETE this file once the real routes land.
 *
 * Shapes mirror src/features/scan/api/types.local.ts; server-side behavior
 * (filter/search/sort/paging/counts) is approximated so the UI is exercisable.
 */
import type { Connect, Plugin } from "vite";

type SectionCounts = { ok?: number; partial?: number; failed?: number; skipped?: number; missing?: number };
type Doc = {
  id: string; method: string | null; uri: string | null; title: string | null;
  document: string; overall_status: string; issues: { code: string; count: number }[];
};

const SECTIONS = ["path_params", "query_params", "headers", "body", "response", "example_request", "example_response"];
const V = "3.2.0";
const NOW = "2026-07-23T09:15:00Z";

const rollup = (ok: number, partial = 0, failed = 0, skipped = 0, missing = 0) =>
  Object.fromEntries(SECTIONS.map((s) => [s, { ok, partial, failed, skipped, missing } as SectionCounts]));

type MockService = {
  name: string; scan_status: string; documents: number | null; struct_ok: number | null;
  scanner_version: string | null; scanned_at: string | null; docs_changed: boolean;
  rescan_reason: string | null; error: string | null;
  job_id?: string; started_by?: string; started_at?: string;
  [k: string]: unknown;
};

const svc = (o: Partial<MockService> & { name: string; scan_status: string }): MockService => ({
  scanner_version: V, scanned_at: NOW, docs_changed: false, rescan_reason: null, error: null,
  overall_breakdown: {}, section_rollup: rollup(0), struct_ok: null, documents: null,
  has_previous: false, top_issues: [], non_endpoint_documents: 0, ...o,
});

const SERVICES = [
  svc({ name: "billing-api", scan_status: "scanned", documents: 42, struct_ok: 97,
    overall_breakdown: { ok: 40, partial: 2 }, section_rollup: rollup(40, 2), has_previous: true,
    top_issues: [{ code: "missing_example", count: 3 }] }),
  svc({ name: "customer-core", scan_status: "scanned", documents: 128, struct_ok: 88, scanner_version: "3.1.0",
    rescan_reason: "version", overall_breakdown: { ok: 110, partial: 12, unsupported: 6 },
    section_rollup: rollup(110, 12, 0, 6), has_previous: true,
    top_issues: [{ code: "unknown_type", count: 14 }, { code: "missing_description", count: 9 }] }),
  svc({ name: "device-mgmt", scan_status: "partial", documents: 31, struct_ok: 64, rescan_reason: "partial",
    overall_breakdown: { ok: 18, partial: 9, failed: 4 }, section_rollup: rollup(18, 9, 4), has_previous: true,
    top_issues: [{ code: "table_parse_error", count: 6 }] }),
  svc({ name: "legacy-soap-bridge", scan_status: "failed", rescan_reason: "retry",
    error: "clone failed: repository archived (HTTP 403)", scanned_at: null, scanner_version: null }),
  svc({ name: "notifications-hub", scan_status: "scanned", documents: 17, struct_ok: 94, docs_changed: true,
    rescan_reason: "drift", overall_breakdown: { ok: 16, partial: 1 }, section_rollup: rollup(16, 1), has_previous: true }),
  svc({ name: "payments-gw", scan_status: "scanning", documents: 55, struct_ok: 91, has_previous: true,
    overall_breakdown: { ok: 50, partial: 5 }, section_rollup: rollup(50, 5),
    job_id: "1042", started_by: "valeriia", started_at: "2026-07-23T12:58:00Z" }),
  svc({ name: "tariff-catalog", scan_status: "scanned", documents: 0, non_endpoint_documents: 7 }),
  svc({ name: "roaming-info", scan_status: "not_scanned", scanned_at: null, scanner_version: null }),
];

const DOCS: Record<string, Doc[]> = {};
for (const s of SERVICES) {
  const n = (s.documents as number) ?? 0;
  DOCS[s.name as string] = Array.from({ length: n }, (_, i) => {
    const status = i % 13 === 5 ? "failed" : i % 7 === 3 ? "partial" : i % 17 === 9 ? "unsupported" : "ok";
    return {
      id: `${s.name}-doc-${i + 1}`,
      method: ["GET", "POST", "PUT", "DELETE", "PATCH"][i % 5],
      uri: `/v2/${s.name}/resource-${i + 1}`,
      title: `Operation ${i + 1} of ${s.name}`,
      document: `api-ref/source/ops/operation-${i + 1}.md`,
      overall_status: status,
      issues: status === "ok" ? [] : [{ code: status === "failed" ? "table_parse_error" : "unknown_type", count: (i % 3) + 1 }],
    };
  }).sort((a, b) => "failed,partial,unsupported,ok".indexOf(a.overall_status) - "failed,partial,unsupported,ok".indexOf(b.overall_status));
}

const detail = (name: string, id: string) => ({
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
          let items = SERVICES.filter((s) => (s.name as string).includes(q));
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

          if (rest === "" && req.method === "GET") return json(res, service);
          if (rest === "/documents") {
            const status = url.searchParams.get("status");
            const page = Number(url.searchParams.get("page") ?? 1);
            const page_size = 15;
            const all = DOCS[name].filter((d) => (d.title ?? "").toLowerCase().includes(q) || d.uri?.toLowerCase().includes(q));
            const doc_counts = Object.fromEntries(
              ["all", "ok", "partial", "failed", "unsupported"].map((k) => [k, k === "all" ? all.length : all.filter((d) => d.overall_status === k).length]),
            );
            const filtered = status ? all.filter((d) => d.overall_status === status) : all;
            return json(res, { items: filtered.slice((page - 1) * page_size, page * page_size), total: filtered.length, page, page_size, doc_counts });
          }
          const dm = rest.match(/^\/documents\/(.+)$/);
          if (dm) return json(res, detail(name, decodeURIComponent(dm[1])));
          if (rest === "/rescan") return json(res, { job_id: String(1043 + Math.floor(Math.random() * 100)) });
          if (rest === "/rollback") return json(res, { current_job_id: "1041", previous_job_id: "998", scanned_at: "2026-07-20T22:10:00Z", scanner_version: "3.1.0" });
          if (rest === "/exclude" || rest === "/include") { res.statusCode = 204; return res.end(); }
        }
        return json(res, { error: { code: "not_found", message: `no mock for ${url.pathname}` } }, 404);
      });
    },
  };
}
