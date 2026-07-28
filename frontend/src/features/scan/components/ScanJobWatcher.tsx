import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { JOB_TERMINAL, invalidateGeneration, invalidateScanFailure, useJob } from "../api/queries";

interface Props {
  serviceName: string;
  jobId: number;
}

/**
 * While a scan job runs, polls it via useJob and refreshes the panel once the
 * job reaches a terminal status. Renders nothing — it only drives cache
 * invalidation: a done job refreshes the full generation set, a failed one
 * only the service state and the aggregates that surface the error.
 */
export function ScanJobWatcher({ serviceName, jobId }: Props) {
  const qc = useQueryClient();
  const { data: job } = useJob(jobId);
  const handled = useRef(false);

  useEffect(() => {
    if (!job) return;
    if (JOB_TERMINAL.has(job.status) && !handled.current) {
      handled.current = true;
      if (job.status === "done") {
        invalidateGeneration(qc, serviceName);
      } else {
        invalidateScanFailure(qc, serviceName);
      }
    }
  }, [job, qc, serviceName]);

  return null;
}
