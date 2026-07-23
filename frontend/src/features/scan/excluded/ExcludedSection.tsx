import { useState } from "react";
import { Ban, ChevronDown, ChevronRight, Undo2 } from "lucide-react";
import { useExcluded } from "../api/queries";
import { useInclude } from "../api/mutations";

function ExcludedRow({ item }: { item: { name: string; reason: string; excluded_by: string; excluded_at: string } }) {
  const include = useInclude(item.name);
  return (
    <div className="flex items-center gap-4 border-b border-gray-100 px-4 py-2.5 last:border-0">
      <span className="w-44 truncate font-mono text-sm text-gray-500" title={item.name}>
        {item.name}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs text-gray-600" title={item.reason}>
          {item.reason}
        </div>
        <div className="font-mono text-[10px] text-gray-400">
          excluded by {item.excluded_by} · {item.excluded_at}
        </div>
      </div>
      <button
        onClick={() => {
          if (
            window.confirm(
              `Restore ${item.name} to the registry?\n\nIt returns with its previous scan data and will be picked up by nightly discovery again.`,
            )
          ) {
            include.mutate();
          }
        }}
        disabled={include.isPending}
        className="flex items-center gap-1.5 whitespace-nowrap rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Undo2 size={12} /> Restore
      </button>
    </div>
  );
}

/** Collapsed managed list at the bottom of the registry (PS19). */
export function ExcludedSection() {
  const [open, setOpen] = useState(false);
  const { data: excluded } = useExcluded();
  if (!excluded) return null;

  return (
    <div className="mt-6">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-400 transition hover:text-gray-600"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Ban size={12} /> Excluded services <span className="font-mono tabular-nums">{excluded.length}</span>
      </button>
      {open &&
        (excluded.length === 0 ? (
          <div className="mt-2 rounded-lg border border-dashed border-gray-200 px-4 py-3 text-xs text-gray-400">
            Nothing excluded. Repos excluded here keep their scan history, disappear from all counts, and are skipped by
            nightly discovery until restored.
          </div>
        ) : (
          <div className="mt-2 overflow-hidden rounded-xl border border-gray-200 bg-white">
            {excluded.map((r) => (
              <ExcludedRow key={r.name} item={r} />
            ))}
          </div>
        ))}
    </div>
  );
}
