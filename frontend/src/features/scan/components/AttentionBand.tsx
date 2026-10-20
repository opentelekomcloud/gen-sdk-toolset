import { ODSCircleAdd, ODSCircleArrowUp, ODSClipboard, ODSEdit, ODSNavigationRight, ODSSuccess, ODSWarning } from "@telekom-ods/react-icons";
import type { IconComponent } from "../../../shared/ui/icon";
import { useNavigate, useSearchParams } from "react-router";
import { useAttention } from "../api/queries";
import type { AttentionRuleCode } from "../types";
import type { AttentionRule } from "../../../shared/api/types";
import { useGenerationAttention } from "../../generation/data/queries";
import type { GenAttentionCode, GenFilter } from "../../generation/data/types";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** Presentation for rule codes; unknown codes fall back gracefully — rules are data. */
const RULE_ICON: Record<AttentionRuleCode | GenAttentionCode, { icon: IconComponent; cls: string }> = {
  failed: { icon: ODSWarning, cls: "text-danger" },
  version: { icon: ODSCircleArrowUp, cls: "text-warning" },
  drift: { icon: ODSEdit, cls: "text-warning" },
  new: { icon: ODSCircleAdd, cls: "text-info" },
  gen_review: { icon: ODSClipboard, cls: "text-on-brand-subtle" },
  gen_failed: { icon: ODSWarning, cls: "text-danger" },
};

/** Known rule codes are localized client-side; unknown codes fall back to the server label. */
const RULE_LABEL_KEY: Record<AttentionRuleCode | GenAttentionCode, MessageKey> = {
  failed: "attention.rule.failed",
  version: "attention.rule.version",
  drift: "attention.rule.drift",
  new: "attention.rule.new",
  gen_review: "attention.rule.gen_review",
  gen_failed: "attention.rule.gen_failed",
};

/** A Generation rule opens the Generation list on the matching filter chip. */
const GEN_RULE_FILTER: Record<GenAttentionCode, GenFilter> = {
  gen_review: "review",
  gen_failed: "failed",
};

/** Where a rule leads; null for a panel that does not exist yet. */
function ruleTarget(r: AttentionRule): string | null {
  if (r.panel === "scan") return `/scan?rule=${r.code}`;
  const filter = r.panel === "generation" ? GEN_RULE_FILTER[r.code] : undefined;
  return filter ? `/generation?filter=${filter}` : null;
}

function AllClear() {
  const { t } = useI18n();
  return (
    <div className="border-b border-neutral-200 bg-surface/70 px-6 py-2">
      <div className="mx-auto flex max-w-6xl items-center gap-2 text-xs font-medium text-success">
        <ODSSuccess decorative size={14} /> {t("attention.allClear")}
      </div>
    </div>
  );
}

/**
 * App-level band between the header and the tab bar (PS18), shared by every
 * panel: scan rules arrive from the API, Generation rules from its data hooks.
 * Clicking navigates to the owning panel pre-filtered (URL-shareable). Domain
 * tags appear only when rules span >1 panel.
 */
export function AttentionBand() {
  const scan = useAttention();
  const gen = useGenerationAttention();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { t } = useI18n();
  const activeRule = searchParams.get("rule");

  // band appears once every panel has answered; no layout jump worth a skeleton
  if (scan.isPending || gen.isPending) return null;
  /* One panel failing must not hide the other's rules, nor pass for "all clear":
     what arrived is shown, and a panel whose rules did not load is named. */
  const rules = [...(scan.data ?? []), ...(gen.data ?? [])];
  const unloaded: MessageKey[] = [];
  if (scan.isError) unloaded.push("tab.scan");
  if (gen.isError) unloaded.push("tab.generation");
  if (rules.length === 0 && unloaded.length === 0) return <AllClear />;
  const showTags = new Set(rules.map((r) => r.panel)).size > 1;

  return (
    <div className="border-b border-neutral-200 bg-surface/70 px-6 py-3">
      <div className="mx-auto max-w-6xl">
        <div className="mb-2 flex items-baseline gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-neutral-700">{t("attention.title")}</span>
          <span className="text-[10px] text-neutral-600">{t("attention.subtitle")}</span>
        </div>
        <div className="flex flex-col gap-2">
          {rules.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {rules.map((r) => {
                const meta = RULE_ICON[r.code];
                const Icon = meta?.icon ?? ODSWarning;
                /* only a scan rule filters by `rule` and toggles back off, as in the prototype */
                const active = r.panel === "scan" && activeRule === r.code;
                const label = RULE_LABEL_KEY[r.code] ? t(RULE_LABEL_KEY[r.code]) : r.label;
                const target = ruleTarget(r);
                return (
                  <button type="button"
                    key={r.code}
                    disabled={!target}
                    title={target ? undefined : t("attention.futurePanel")}
                    onClick={() => target && navigate(active ? "/scan" : target)}
                    className={`group flex items-center gap-2.5 rounded-lg border bg-surface px-3 py-2 text-left transition ${
                      active
                        ? "border-brand ring-1 ring-brand"
                        : target
                          ? "border-neutral-200 hover:border-neutral-500"
                          : "cursor-not-allowed border-dashed border-neutral-200 bg-surface/60"
                    }`}
                  >
                    <Icon decorative size={15} className={meta?.cls ?? "text-neutral-600"} />
                    <span className="font-mono text-lg font-semibold tabular-nums text-ink">{r.count}</span>
                    <span className="max-w-[150px] text-xs leading-tight text-ink-recessive">{label}</span>
                    {showTags && (
                      <span
                        className={`rounded px-1 py-px text-[9px] font-medium uppercase tracking-wide ${
                          r.panel === "generation" ? "bg-brand-subtle text-on-brand-subtle" : "bg-neutral-100 text-neutral-600"
                        }`}
                      >
                        {r.panel}
                      </span>
                    )}
                    {target && (
                      <ODSNavigationRight decorative
                        size={13}
                        className={active ? "text-brand-text" : "text-neutral-400 transition group-hover:text-neutral-700"}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          )}
          {unloaded.map((panel) => (
            <div key={panel} role="alert" className="flex items-center gap-1.5 text-xs font-medium text-danger">
              <ODSWarning decorative size={14} /> {t("attention.loadFailed", { panel: t(panel) })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
