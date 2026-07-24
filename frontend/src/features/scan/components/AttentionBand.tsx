import { AlertTriangle, ArrowUpCircle, CheckCircle2, ChevronRight, GitCommit, PlusCircle, type LucideIcon } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router";
import { useAttention } from "../api/queries";
import type { AttentionRuleCode } from "../api/types.local";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** Presentation for rule codes; unknown codes fall back gracefully — rules are data. */
const RULE_ICON: Record<AttentionRuleCode, { icon: LucideIcon; cls: string }> = {
  failed: { icon: AlertTriangle, cls: "text-red-500" },
  version: { icon: ArrowUpCircle, cls: "text-amber-500" },
  drift: { icon: GitCommit, cls: "text-amber-500" },
  new: { icon: PlusCircle, cls: "text-blue-500" },
};

/** Known rule codes are localized client-side; unknown codes fall back to the server label. */
const RULE_LABEL_KEY: Record<AttentionRuleCode, MessageKey> = {
  failed: "attention.rule.failed",
  version: "attention.rule.version",
  drift: "attention.rule.drift",
  new: "attention.rule.new",
};

function AllClear() {
  const { t } = useI18n();
  return (
    <div className="border-b border-gray-200 bg-white/70 px-6 py-2">
      <div className="mx-auto flex max-w-6xl items-center gap-2 text-xs font-medium text-emerald-600">
        <CheckCircle2 size={14} /> {t("attention.allClear")}
      </div>
    </div>
  );
}

/**
 * App-level band between the header and the tab bar (PS18). Rules arrive
 * from the API as data; clicking navigates to the owning panel pre-filtered
 * (URL-shareable). Domain tags appear only when rules span >1 panel.
 */
export function AttentionBand() {
  const { data: rules } = useAttention();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { t } = useI18n();
  const activeRule = searchParams.get("rule");

  if (!rules) return null; // band appears when data arrives; no layout jump worth a skeleton
  if (rules.length === 0) return <AllClear />;
  const showTags = new Set(rules.map((r) => r.panel)).size > 1;

  return (
    <div className="border-b border-gray-200 bg-white/70 px-6 py-3">
      <div className="mx-auto max-w-6xl">
        <div className="mb-2 flex items-baseline gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{t("attention.title")}</span>
          <span className="text-[10px] text-gray-400">{t("attention.subtitle")}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {rules.map((r) => {
            const meta = RULE_ICON[r.code];
            const Icon = meta?.icon ?? AlertTriangle;
            const active = activeRule === r.code;
            const label = RULE_LABEL_KEY[r.code] ? t(RULE_LABEL_KEY[r.code]) : r.label;
            /* today every rule targets the scan registry; future rules navigate to their panel */
            const target = r.panel === "scan" ? `/scan?rule=${r.code}` : null;
            return (
              <button
                key={r.code}
                disabled={!target}
                title={target ? undefined : t("attention.futurePanel")}
                onClick={() => target && navigate(active ? "/scan" : target)}
                className={`group flex items-center gap-2.5 rounded-lg border bg-white px-3 py-2 text-left transition ${
                  active
                    ? "border-brand ring-1 ring-brand"
                    : target
                      ? "border-gray-200 hover:border-gray-400"
                      : "cursor-not-allowed border-dashed border-gray-200 bg-white/60"
                }`}
              >
                <Icon size={15} className={meta?.cls ?? "text-gray-400"} />
                <span className="font-mono text-lg font-semibold tabular-nums text-gray-900">{r.count}</span>
                <span className="max-w-[150px] text-xs leading-tight text-gray-600">{label}</span>
                {showTags && (
                  <span className="rounded bg-gray-100 px-1 py-px text-[9px] font-medium uppercase tracking-wide text-gray-400">
                    {r.panel}
                  </span>
                )}
                {target && (
                  <ChevronRight
                    size={13}
                    className={active ? "text-brand" : "text-gray-300 transition group-hover:text-gray-500"}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
