import { Link } from "react-router";
import type { GenJob, GenJobStatus } from "../data/types";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** A job is drawn as a tag - uppercase and smaller than the state pill, as in the prototype. */
const JOB_CLS: Record<GenJobStatus, string> = {
  running: "border-info-line bg-info-subtle text-info",
  done: "border-warning-line bg-warning-subtle text-warning",
  merged: "border-brand-line bg-brand-subtle text-on-brand-subtle",
  failed: "border-danger-line bg-danger-subtle text-danger",
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
