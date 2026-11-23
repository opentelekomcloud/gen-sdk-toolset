import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";

/** A Generation page with a line in place of its content: the way `back`, why, and where to go instead. */
export function PageMessage({
  back,
  note,
  link,
}: {
  back: ReactNode;
  note: string;
  link?: { to: string; label: string };
}) {
  const { state: fromList } = useLocation();
  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}
      <div className="py-16 text-center text-sm text-gray-400">
        {note}
        {link && (
          <Link
            to={link.to}
            state={fromList}
            className="mx-auto mt-3 flex w-fit items-center gap-1.5 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-gray-500"
          >
            {link.label}
          </Link>
        )}
      </div>
    </div>
  );
}
