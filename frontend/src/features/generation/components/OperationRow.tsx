import { ExternalLink } from "lucide-react";
import type { GenOperationKind } from "../data/types";
import { methodCls } from "../../scan/styles";
import { useI18n, type MessageKey } from "../../../shared/i18n";

const KIND_CLS: Record<GenOperationKind, string> = {
  base: "border-blue-200 bg-blue-50 text-blue-700",
  custom: "border-purple-200 bg-purple-50 text-purple-700",
};

/** One operation of a resource: its kind, its source endpoint, and its SDK call, or why it has none. */
export function OperationRow({
  title,
  kind,
  method,
  uri,
  call,
  missing,
  href,
}: {
  title: string;
  kind: GenOperationKind;
  method: string;
  uri: string;
  call: string | null;
  missing?: string;
  href: string;
}) {
  const { t } = useI18n();
  return (
    <div
      role="group"
      aria-label={title}
      className="grid grid-cols-12 items-center gap-3 border-b border-gray-100 px-4 py-2 last:border-0"
    >
      <div className="col-span-3 truncate text-xs text-gray-600" title={title}>
        {title}
      </div>
      <div className="col-span-2">
        <span
          className={`rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${KIND_CLS[kind]}`}
        >
          {t(`gen.spec.kind.${kind}` as MessageKey)}
        </span>
      </div>
      <div className="col-span-4 flex min-w-0 items-center gap-2">
        <span
          className={`inline-block w-14 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[11px] font-semibold ${methodCls(method)}`}
        >
          {method}
        </span>
        <span className="truncate font-mono text-[11px] text-gray-500" title={uri}>
          {uri}
        </span>
      </div>
      <div className="col-span-3 flex min-w-0 items-center gap-2">
        {call ? (
          <span className="truncate font-mono text-[11px] text-gray-800">{call}</span>
        ) : (
          <span className="truncate text-[11px] text-gray-400" title={missing}>
            — {missing}
          </span>
        )}
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          title={t("doc.openSourceHint")}
          className="ml-auto flex items-center text-gray-400 transition hover:text-gray-700"
        >
          <ExternalLink size={13} />
        </a>
      </div>
    </div>
  );
}
