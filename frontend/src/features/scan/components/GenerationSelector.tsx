import { useEffect, useState } from "react";
import { ChevronDown, GitCommit, History, Loader2 } from "lucide-react";
import { useGenerations } from "../api/queries";
import type { Generation, ServiceDetail } from "../api/types.local";
import { fmtGenAt, shortCommit, structPct } from "../lib/generation";
import { structOkCls } from "../styles";
import { useI18n } from "../../../shared/i18n";

interface Props {
  service: ServiceDetail;
  disabled?: boolean;
  onActivate: (generationId: number) => void;
}

/**
 * G1: compact selector of the active scan generation.
 * Trigger renders from service.active_generation (no extra request); the
 * popover lazily loads the history via GET …/generations. Activating an OLDER
 * generation asks inline confirmation; switching forward to latest applies
 * immediately. Never triggers a scan — only changes which persisted snapshot
 * is active.
 */
export function GenerationSelector({ service, disabled, onActivate }: Props) {
  const [open, setOpen] = useState(false);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const { t, locale } = useI18n();
  const active = service.active_generation;
  const latest = service.latest_generation;
  const { data, isPending } = useGenerations(service.name, open);

  /* Escape closes the popover — click-away alone is mouse-only (a11y) */
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setPendingId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!active) {
    /* failed / never scanned — no persisted snapshots to pick from */
    return (
      <div className="mt-1 font-mono text-xs text-gray-400">
        {service.scanner_version ? t("gen.scannedWith", { v: service.scanner_version }) : t("gen.neverScanned")}
        {service.scanned_at ? ` · ${fmtGenAt(service.scanned_at, locale)}` : ""}
      </div>
    );
  }

  const onLatest = latest == null || active.id === latest.id;
  const close = () => {
    setOpen(false);
    setPendingId(null);
  };
  const pick = (g: Generation) => {
    if (g.id === active.id) return close();
    if (latest && g.id !== latest.id) return setPendingId(g.id); // older snapshot → confirm
    onActivate(g.id);
    close();
  };
  const items = data?.items ?? [];
  const pending = pendingId != null ? items.find((g) => g.id === pendingId) : undefined;

  return (
    <div className="relative mt-1.5 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => !disabled && (open ? close() : setOpen(true))}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="listbox"
        title={t("gen.pillTitle")}
        className={`flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-xs transition ${
          disabled
            ? "cursor-not-allowed border-gray-200 bg-white text-gray-300"
            : onLatest
              ? "border-gray-300 bg-white text-gray-500 hover:border-gray-500 hover:text-gray-800"
              : "border-amber-300 bg-amber-50 text-amber-800 hover:border-amber-500"
        }`}
      >
        <History size={12} className={onLatest ? "text-gray-400" : "text-amber-500"} />
        <span className="font-semibold">{t("gen.pill", { id: active.id })}</span>
        <span className="opacity-40">·</span>
        <span>{fmtGenAt(active.created_at, locale)}</span>
        <span className="opacity-40">·</span>
        <span className="flex items-center gap-1">
          <GitCommit size={11} /> {shortCommit(active.commit_hash)}
        </span>
        <span className="opacity-40">·</span>
        <span>{t("gen.scannerV", { v: active.scanner_version })}</span>
        {!onLatest && (
          <span className="rounded-sm bg-amber-200/70 px-1 py-px text-[10px] font-semibold uppercase tracking-wide">
            {t("gen.notLatest")}
          </span>
        )}
        <ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""}`} />
      </button>
      {service.docs_changed && <span className="font-mono text-xs text-amber-600">{t("gen.headMoved")}</span>}

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={close} />
          <div className="absolute left-0 top-full z-30 mt-1.5 w-[460px] overflow-hidden rounded-lg border border-gray-200 bg-white shadow-xl">
            <div className="border-b border-gray-100 px-3.5 py-2.5">
              <div className="text-xs font-semibold text-gray-700">{t("gen.popoverTitle")}</div>
              <div className="mt-0.5 text-[11px] leading-relaxed text-gray-400">{t("gen.popoverHint")}</div>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {isPending ? (
                <div className="flex items-center gap-2 px-3.5 py-4 text-xs text-gray-400">
                  <Loader2 size={13} className="animate-spin" /> {t("gen.loading")}
                </div>
              ) : (
                items.map((g, i) => {
                  const isActive = g.id === active.id;
                  const pct = structPct(g.completeness);
                  return (
                    <button
                      key={g.id}
                      type="button"
                      onClick={() => pick(g)}
                      className={`flex w-full items-center justify-between gap-3 border-b border-gray-50 px-3.5 py-2.5 text-left transition last:border-0 ${
                        isActive ? "bg-gray-50" : pendingId === g.id ? "bg-amber-50" : "hover:bg-gray-50"
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-semibold text-gray-800">{t("gen.pill", { id: g.id })}</span>
                          {i === 0 && (
                            <span className="rounded-full border border-gray-200 px-1.5 py-px text-[10px] font-medium text-gray-500">
                              {t("gen.latestBadge")}
                            </span>
                          )}
                          {isActive && (
                            <span className="rounded-full bg-brand px-1.5 py-px text-[10px] font-semibold text-white">
                              {t("gen.activeBadge")}
                            </span>
                          )}
                          {g.incomplete_reason && (
                            <span
                              title={g.incomplete_reason}
                              className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-px text-[10px] font-medium text-amber-700"
                            >
                              {t("gen.incompleteBadge")}
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-gray-400">
                          <span>{fmtGenAt(g.created_at, locale)}</span>
                          <span className="flex items-center gap-1">
                            <GitCommit size={10} /> {shortCommit(g.commit_hash)}
                          </span>
                          <span>{t("gen.scannerV", { v: g.scanner_version })}</span>
                        </div>
                      </div>
                      <div className="shrink-0 text-right font-mono text-[11px] tabular-nums text-gray-500">
                        {t("gen.docs", { n: g.documents_total })}
                        <br />
                        <span className={structOkCls(pct)}>{pct == null ? "—" : `${pct}%`}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
            {pending && latest && (
              <div className="border-t border-amber-200 bg-amber-50 px-3.5 py-3">
                <div className="text-xs font-semibold text-amber-900">{t("gen.confirmTitle", { id: pending.id })}</div>
                <p className="mt-1 text-[11px] leading-relaxed text-amber-800">
                  {t("gen.confirmBody", {
                    at: fmtGenAt(pending.created_at, locale),
                    ver: pending.scanner_version,
                    commit: shortCommit(pending.commit_hash),
                    latest: latest.id,
                  })}
                </p>
                <div className="mt-2 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setPendingId(null)}
                    className="rounded border border-amber-300 px-2.5 py-1 text-xs font-medium text-amber-800 transition hover:border-amber-500"
                  >
                    {t("gen.cancel")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onActivate(pending.id);
                      close();
                    }}
                    className="rounded bg-brand px-2.5 py-1 text-xs font-semibold text-white transition hover:opacity-90"
                  >
                    {t("gen.setActive")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
