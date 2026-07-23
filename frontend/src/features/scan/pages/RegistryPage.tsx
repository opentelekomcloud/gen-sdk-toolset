import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ChevronRight, Search } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router";
import { useRescan } from "../api/mutations";
import { useServices, useSummary, type ServicesParams } from "../api/queries";
import type { AttentionRuleCode, ServiceFilter, ServiceListItem, ServiceSort } from "../api/types.local";
import { RescanButton } from "../components/RescanButton";
import { SectionStrip } from "../components/SectionStrip";
import { StatusPill } from "../components/StatusPill";
import { OverallBar } from "../components/OverallBar";
import { ExcludedSection } from "../excluded/ExcludedSection";
import { chipCls, structOkCls } from "../styles";

const CHIPS: [ServiceFilter, string][] = [
  ["all", "All"],
  ["scanned", "Scanned"],
  ["partial", "Partial"],
  ["failed", "Failed"],
  ["not_scanned", "Not scanned"],
  ["scanning", "In progress"],
  ["needs_rescan", "Needs rescan"],
];

function ServiceRow({ item, scannerVersion }: { item: ServiceListItem; scannerVersion: string }) {
  const navigate = useNavigate();
  const rescan = useRescan(item.name);
  const outdated = item.scanner_version != null && item.scanner_version !== scannerVersion;

  return (
    <div
      className={`grid cursor-pointer grid-cols-12 items-center gap-3 border-b border-gray-100 px-4 py-2.5 transition last:border-0 hover:bg-gray-50 ${
        item.scan_status === "scanning" ? "bg-blue-50/40" : ""
      }`}
      onClick={() => navigate(`/scan/services/${encodeURIComponent(item.name)}`)}
    >
      <div className="col-span-3 flex items-center gap-1.5 overflow-hidden">
        <ChevronRight size={14} className="shrink-0 text-gray-400" />
        <span className="truncate font-mono text-sm text-gray-800">{item.name}</span>
      </div>
      <div className="col-span-2">
        <StatusPill kind={item.scan_status} by={item.started_by} />
      </div>
      <div className="col-span-3">
        {item.documents ? (
          <div className="space-y-1">
            <div className="font-mono text-xs tabular-nums text-gray-600">
              {item.documents} docs · <span className={structOkCls(item.struct_ok)}>{item.struct_ok}%</span>
              {outdated && <span className="text-gray-400"> · v{item.scanner_version}</span>}
            </div>
            <OverallBar overall={item.overall_breakdown} docs={item.documents} />
          </div>
        ) : item.scan_status === "failed" ? (
          <span className="truncate text-xs text-red-600">{item.error}</span>
        ) : item.scan_status === "scanning" ? (
          <span className="text-xs text-blue-600">scanning…</span>
        ) : (
          <span className="text-xs text-gray-400">{item.documents === 0 ? "no endpoint docs" : "—"}</span>
        )}
      </div>
      <div className="col-span-2">
        <SectionStrip sections={item.documents ? item.section_rollup : null} />
      </div>
      <div className="col-span-2 text-right" onClick={(e) => e.stopPropagation()}>
        <RescanButton
          reason={item.rescan_reason}
          scanning={item.scan_status === "scanning" ? { jobId: item.job_id, startedBy: item.started_by } : undefined}
          scannerVersion={scannerVersion}
          onClick={() => rescan.mutate()}
        />
      </div>
    </div>
  );
}

/** Registry (PS10): filter/search/sort/rule round-trip through the URL and the API. */
export function RegistryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const params: ServicesParams = {
    status: (searchParams.get("status") as ServiceFilter) ?? "all",
    q: searchParams.get("q") ?? "",
    sort: (searchParams.get("sort") as ServiceSort) ?? "quality",
    rule: (searchParams.get("rule") as AttentionRuleCode) ?? undefined,
  };
  const setParam = useCallback(
    (key: string, value: string, dropRule = false) =>
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value && value !== "all") next.set(key, value);
          else next.delete(key);
          if (dropRule) next.delete("rule");
          return next;
        },
        { replace: true },
      ),
    [setSearchParams],
  );

  /* Debounced search: keystrokes land in local state; the URL (and the API
     request behind it) updates 300 ms after typing stops. */
  const [qInput, setQInput] = useState(params.q ?? "");
  useEffect(() => {
    const t = setTimeout(() => setParam("q", qInput), 300);
    return () => clearTimeout(t);
  }, [qInput, setParam]);

  const { data } = useServices(params);
  const { data: summary } = useSummary();
  const scannerVersion = summary?.scanner_version ?? "";

  return (
    <>
      {summary && summary.failed_services > 0 && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-6 py-2 text-xs text-amber-800">
          <AlertTriangle size={14} />
          {summary.failed_services} repos failed and hold no data. Metrics cover{" "}
          {summary.services_total - summary.failed_services} scanned repos.
        </div>
      )}
      <div className="mx-auto max-w-6xl px-6 py-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {CHIPS.map(([k, label]) => (
            <button key={k} onClick={() => setParam("status", k, true)} className={chipCls(params.status === k && !params.rule)}>
              {label} <span className="font-mono tabular-nums opacity-70">{data?.counts[k] ?? 0}</span>
            </button>
          ))}
          <div className="relative ml-auto">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="Filter services…"
              className="w-48 rounded-md border border-gray-300 bg-white py-1.5 pl-8 pr-3 text-sm outline-none transition focus:border-gray-500"
            />
          </div>
          <select
            value={params.sort}
            onChange={(e) => setParam("sort", e.target.value)}
            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-600 outline-none"
          >
            <option value="quality">Worst quality first</option>
            <option value="docs">Most docs first</option>
            <option value="name">By name</option>
          </select>
        </div>

        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="grid grid-cols-12 gap-3 border-b border-gray-200 bg-gray-50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            <div className="col-span-3">Service</div>
            <div className="col-span-2">Scan status</div>
            <div className="col-span-3">Docs · quality</div>
            <div className="col-span-2">Sections</div>
            <div className="col-span-2 text-right">Rescan</div>
          </div>
          {data?.items.map((item) => (
            <ServiceRow key={item.name} item={item} scannerVersion={scannerVersion} />
          ))}
          {data && data.items.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-400">No services match the current filter.</div>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-gray-400">
          <span>
            scanner v{scannerVersion}
            {summary?.last_scanned_at ? ` · last update ${summary.last_scanned_at}` : ""}
          </span>
          <span className="flex items-center gap-3">
            <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-500" /> ok</span>
            <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-amber-400" /> partial</span>
            <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-red-500" /> failed</span>
            <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-gray-200" /> no section</span>
          </span>
        </div>

        <ExcludedSection />
      </div>
    </>
  );
}
