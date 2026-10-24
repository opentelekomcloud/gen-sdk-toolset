import { useEffect, useState } from "react";
import { ODSClose, ODSFile, ODSNavigationLeft, ODSNavigationRight, ODSSearch } from "@telekom-ods/react-icons";
import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { useDocuments } from "../api/queries";
import { fieldCls } from "../../../shared/ui/field";
import type { DocFilter, DocStatus } from "../types";
import { sectionLabelKey, UNVERSIONED } from "../constants";
import { chipCls } from "../styles";
import { DocRow } from "./DocRow";
import { useI18n, type MessageKey } from "../../../shared/i18n";

const CHIP_ORDER: (DocStatus | "all")[] = ["all", "failed", "unsupported", "partial", "ok"];

/** Documents block on the service page (PS12): server-side filter/search/pagination. */
interface Props {
  serviceName: string;
  /** Set by clicking a section count or a top-issue chip. */
  filter?: DocFilter | null;
  onClearFilter?: () => void;
}

export function DocumentsBlock({ serviceName, filter, onClearFilter }: Props) {
  const [status, setStatus] = useState<DocStatus | "all">("all");
  const [version, setVersion] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [page, setPage] = useState(1);
  const { t } = useI18n();

  /* Debounce keystrokes so each letter doesn't fire an API request. */
  useEffect(() => {
    const timer = setTimeout(() => setQDebounced(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  const { data } = useDocuments(serviceName, {
    status,
    q: qDebounced,
    page,
    section: filter?.kind === "section" ? filter.section : undefined,
    section_status: filter?.kind === "section" ? filter.status : undefined,
    issue: filter?.kind === "issue" ? filter.code : undefined,
    api_version: version ?? undefined,
  });
  if (!data) return null;

  const chips = CHIP_ORDER.filter((k) => k === "all" || data.doc_counts[k]);
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  const from = (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.page * data.page_size, data.total);

  return (
    <>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <ODSFile decorative size={15} className="text-neutral-600" />
        <span className="text-sm font-semibold text-ink-recessive">{t("docs.title")}</span>
        {chips.map((k) => (
          <button type="button"
            key={k}
            onClick={() => {
              setStatus(k);
              setPage(1);
            }}
            className={chipCls(status === k)}
          >
            {t(`docstatus.${k}` as MessageKey)} <span className="font-mono tabular-nums opacity-70">{data.doc_counts[k] ?? 0}</span>
          </button>
        ))}
        {/* Versions come from the same response as the rows, so the chips can
            never claim a version the current filter has no documents for. */}
        {Object.keys(data.version_counts).length > 1 &&
          Object.entries(data.version_counts)
            /* Numbered versions first, "no version" last: it is a leftover
               bucket, not a version anyone released. */
            .sort(([a], [b]) =>
              a === UNVERSIONED ? 1 : b === UNVERSIONED ? -1 : a.localeCompare(b),
            )
            .map(([name, count]) => (
              <button type="button"
                key={name}
                onClick={() => {
                  setVersion(version === name ? null : name);
                  setPage(1);
                }}
                className={chipCls(version === name)}
              >
                {name === UNVERSIONED ? t("docs.noVersion") : name}{" "}
                <span className="font-mono tabular-nums opacity-70">{count}</span>
              </button>
            ))}
        {filter && (
          <button
            type="button"
            onClick={onClearFilter}
            className="inline-flex h-8 items-center gap-1.5 rounded-full bg-contrast px-3.5 text-sm font-medium text-on-contrast transition hover:opacity-80"
          >
            {filter.kind === "section"
              ? `${t(sectionLabelKey(filter.section))} · ${filter.status}`
              : filter.code}
            <ODSClose decorative size={14} />
          </button>
        )}
        <div className="relative ml-auto">
          <ODSSearch decorative size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder={t("docs.filter")}
            aria-label={t("docs.filter")}
            className={`${fieldCls} w-56 pl-9`}
          />
        </div>
      </div>

      {/* wide rows scroll inside the card on a narrow screen instead of squeezing */}
      <div className="overflow-x-auto rounded-xl border border-neutral-200 bg-surface">
        <div className="min-w-[56rem]">
          {data.items.map((doc) => (
            <DocRow key={doc.id} serviceName={serviceName} doc={doc} />
          ))}
          {data.items.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-neutral-600">{t("docs.empty")}</div>
          )}
        </div>
      </div>

      {data.total > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-ink-recessive">
          <span>{t("docs.showing", { from, to, total: data.total })}</span>
          <span className="flex items-center gap-2">
            <ODSButton
              size="small"
              variant="outline"
              label={t("docs.prev")}
              buttonIcon={<ODSNavigationLeft decorative />}
              leftIcon
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={data.page <= 1}
            />
            <span className="px-1 font-mono tabular-nums">{t("docs.page", { p: data.page, total: totalPages })}</span>
            <ODSButton
              size="small"
              variant="outline"
              label={t("docs.next")}
              buttonIcon={<ODSNavigationRight decorative />}
              rightIcon
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={data.page >= totalPages}
            />
          </span>
        </div>
      )}
    </>
  );
}
