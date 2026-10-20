import type { DocStatus } from "../types";

const PARTS: [DocStatus, string][] = [
  ["ok", "bg-success"],
  ["partial", "bg-warning-fill"],
  ["failed", "bg-danger"],
  ["unsupported", "bg-neutral-400"],
];

/**
 * Status shares of one snapshot. Documents that were not read in full are
 * taken OUT of their colour and shown as one grey slice at the end: they are
 * already counted in a status, and painting them twice would overstate the
 * bar. Grey therefore reads as "we cannot vouch for these yet".
 */
export function OverallBar({
  overall,
  docs,
  unread,
}: {
  overall: Partial<Record<DocStatus, number>> | null;
  docs: number | null;
  unread?: Partial<Record<DocStatus, number>> | null;
}) {
  if (!overall || !docs) return null;
  const unreadTotal = Object.values(unread ?? {}).reduce((sum, n) => sum + (n ?? 0), 0);
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
      {PARTS.map(([k, cls]) => {
        const read = (overall[k] ?? 0) - (unread?.[k] ?? 0);
        return read > 0 ? <div key={k} className={cls} style={{ width: `${(100 * read) / docs}%` }} /> : null;
      })}
      {unreadTotal > 0 && (
        <div
          className="bg-neutral-300"
          style={{ width: `${(100 * unreadTotal) / docs}%` }}
          title={`${unreadTotal} not read in full`}
        />
      )}
    </div>
  );
}
