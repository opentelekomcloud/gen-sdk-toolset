import { Link } from "react-router";
import type { GenJob, GenJobStatus } from "../data/types";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** A job is drawn as a tag - uppercase and smaller than the state pill, as in the prototype. */
const JOB_CLS: Record<GenJobStatus, string> = {
  running: "border-blue-200 bg-blue-50 text-blue-700",
  done: "border-amber-200 bg-amber-50 text-amber-800",
  merged: "border-violet-200 bg-violet-50 text-violet-700",
  failed: "border-red-300 bg-red-50 text-red-700",
};

/** A resource's generation job on a target, with its pull request once it has one; it leads to the job's result. */
export function JobTag({ job, to, state }: { job: GenJob; to: string; state?: unknown }) {
  const { t } = useI18n();
  return (
    <Link
      to={to}
      state={state}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-[3px] text-[10px] font-semibold uppercase tracking-wide ${JOB_CLS[job.status]}`}
    >
      {[t(`gen.job.${job.status}` as MessageKey), job.pr != null ? t("gen.job.pr", { pr: job.pr }) : null]
        .filter(Boolean)
        .join(" · ")}
    </Link>
  );
}
