import type { DocStatus } from "../api/types.local";

const PARTS: [DocStatus, string][] = [
  ["ok", "bg-emerald-500"],
  ["partial", "bg-amber-400"],
  ["failed", "bg-red-500"],
  ["unsupported", "bg-gray-400"],
];

export function OverallBar({
  overall,
  docs,
}: {
  overall: Partial<Record<DocStatus, number>> | null;
  docs: number | null;
}) {
  if (!overall || !docs) return null;
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
      {PARTS.map(([k, cls]) =>
        overall[k] ? <div key={k} className={cls} style={{ width: `${(100 * overall[k]!) / docs}%` }} /> : null,
      )}
    </div>
  );
}
