import { useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { useGenerationServices, useGenerationTargets } from "../data/queries";
import type { GenFilter, GenService, GenState, GenTarget } from "../data/types";
import { servicePath, type FromList } from "../lib/paths";
import { StatusPill } from "../../scan/components/StatusPill";
import { chipCls } from "../../scan/styles";
import { useI18n, type MessageKey } from "../../../shared/i18n";

const CHIPS: GenFilter[] = ["all", "not_generated", "in_progress", "failed", "review", "partial"];

const STATE_CLS: Record<GenState, string> = {
  not_generated: "bg-gray-100 text-gray-500 border-gray-200",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  review: "bg-violet-50 text-violet-700 border-violet-200",
  partial: "bg-amber-50 text-amber-700 border-amber-200",
  done: "bg-violet-50 text-violet-700 border-violet-200",
};
/** A target that is not connected and has nothing generated. */
const NOT_CONNECTED_CLS = "bg-white text-gray-400 border-gray-200";

const stateKey = (s: GenState): MessageKey => `gen.state.${s}` as MessageKey;

/** The service takes half the row and the targets share the rest, however many there are. */
const gridCols = (targets: number) => ({ gridTemplateColumns: `minmax(0,2fr) repeat(${targets}, minmax(0,1fr))` });

function ServiceRow({ service, targets }: { service: GenService; targets: GenTarget[] }) {
  const navigate = useNavigate();
  const { search } = useLocation();
  const { t } = useI18n();
  const [defaultTarget] = targets;
  const open = (target: GenTarget) =>
    navigate(servicePath(service.name, target, defaultTarget), { state: { listSearch: search } satisfies FromList });

  return (
    <div
      style={gridCols(targets.length)}
      className="grid cursor-pointer items-center gap-3 border-b border-gray-100 px-4 py-2.5 transition last:border-0 hover:bg-gray-50"
      onClick={() => open(defaultTarget)}
    >
      <div className="flex items-center gap-1.5 overflow-hidden">
        <ChevronRight size={14} className="shrink-0 text-gray-400" />
        <span className="truncate font-mono text-sm text-gray-800">{service.name}</span>
      </div>
      {targets.map((target) => {
        const { state, merged, total } = service.targets[target.id];
        const notConnected = !target.live && state === "not_generated";
        const label = notConnected ? t("gen.target.notConnected") : t(stateKey(state));
        const base = targets.find((x) => x.id === target.base);
        const title = [
          target.label,
          label,
          total ? t("gen.cell.merged", { n: merged, total }) : null,
          base ? t("gen.cell.buildsOn", { base: base.label }) : null,
        ]
          .filter(Boolean)
          .join(" · ");
        return (
          <div key={target.id} className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              title={title}
              onClick={(e) => {
                e.stopPropagation();
                open(target);
              }}
            >
              <StatusPill
                cls={notConnected ? NOT_CONNECTED_CLS : STATE_CLS[state]}
                label={label}
                running={state === "in_progress"}
              />
            </button>
            {total > 0 && (
              <span className="font-mono text-[11px] text-gray-400">
                {merged}/{total}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Generation list: services by target; the filter chip round-trips through the URL. */
export function GenerationListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const { data: targets } = useGenerationTargets();
  const { data: services } = useGenerationServices();
  const filter = (searchParams.get("filter") as GenFilter) ?? "all";

  const setFilter = (next: GenFilter) =>
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "all") params.delete("filter");
        else params.set("filter", next);
        return params;
      },
      { replace: true },
    );

  /* The list works on the default target, as the prototype does at #/generation.
     A service merged there in full has left Generation (prototype: "fully merged
     services live in Maintenance, not here"). */
  const defaultTarget = targets?.[0];
  const stateOf = (s: GenService) => (defaultTarget ? s.targets[defaultTarget.id].state : undefined);
  const q = query.toLowerCase();
  const inList =
    defaultTarget && services
      ? services.filter((s) => stateOf(s) !== "done" && s.name.toLowerCase().includes(q))
      : [];
  const count = (f: GenFilter) => (f === "all" ? inList.length : inList.filter((s) => stateOf(s) === f).length);
  const rows = inList.filter((s) => filter === "all" || stateOf(s) === filter);

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <div className="mb-3 text-xs text-gray-400">
        {t("gen.list.eligible")} {targets && t("gen.list.editions", { n: targets.length })}
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {CHIPS.map((k) => (
          <button type="button" key={k} onClick={() => setFilter(k)} className={chipCls(filter === k)}>
            {k === "all" ? t("filter.all") : t(stateKey(k))}{" "}
            <span className="font-mono tabular-nums opacity-70">{count(k)}</span>
          </button>
        ))}
        <div className="relative ml-auto">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("registry.search")}
            className="w-48 rounded-md border border-gray-300 bg-white py-1.5 pl-8 pr-3 text-sm outline-none transition focus:border-gray-500"
          />
        </div>
      </div>

      {targets && services && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div
            style={gridCols(targets.length)}
            className="grid gap-3 border-b border-gray-200 bg-gray-50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500"
          >
            <div>{t("registry.col.service")}</div>
            {targets.map((target) => (
              <div key={target.id}>
                {target.label}
                {!target.live && ` · ${t("gen.col.tbd")}`}
              </div>
            ))}
          </div>
          {rows.map((s) => (
            <ServiceRow key={s.name} service={s} targets={targets} />
          ))}
          {rows.length === 0 && <div className="px-4 py-10 text-center text-sm text-gray-400">{t("registry.empty")}</div>}
        </div>
      )}
    </div>
  );
}
