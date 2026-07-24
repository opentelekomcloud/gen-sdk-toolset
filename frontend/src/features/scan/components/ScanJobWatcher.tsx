import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { JOB_TERMINAL, invalidateGeneration, useJob } from "../api/queries";

interface Props {
  serviceName: string;
  jobId: number;
}

/**
 * F8: while a scan job runs, polls it via useJob and refreshes the panel once
 * the job reaches a terminal status (done/failed). Renders nothing — it only
 * drives cache invalidation; the refreshed ServiceDetail carries the new
 * generation (done) or the error (failed).
 */
export function ScanJobWatcher({ serviceName, jobId }: Props) {
  const qc = useQueryClient();
  const { data: job } = useJob(jobId);
  const handled = useRef(false);

  useEffect(() => {
    if (!job) return;
    if (JOB_TERMINAL.includes(job.status) && !handled.current) {
      handled.current = true;
      invalidateGeneration(qc, serviceName);
    }
  }, [job, qc, serviceName]);

  return null;
}
