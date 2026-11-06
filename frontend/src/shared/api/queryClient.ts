import { QueryClient } from "@tanstack/react-query";

/**
 * How often every mounted query is fetched again from the server (ADR-0076).
 *
 * A visible tab has to show a change no later than 15 s after it is saved on
 * the server (ADR-0077); the 5 s left over cover the response time, which is
 * longest for summary and attention - both recompute every service.
 */
export const REFETCH_INTERVAL_MS = 10_000;

/**
 * The query client the panel runs with.
 *
 * `refetchInterval` is a default rather than a per-hook option, so it applies
 * only to what is on screen: TanStack Query polls mounted queries only. The
 * Header and the Attention Band are mounted on every page, so they refresh
 * everywhere; a page that is not open is not fetched (ADR-0078).
 *
 * `gcTime: 0` drops a query's cache as soon as nothing shows it, so a page
 * opened again loads from the server instead of showing the previous visit
 * (ADR-0078).
 */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 15_000, retry: 1, refetchInterval: REFETCH_INTERVAL_MS, gcTime: 0 },
    },
  });
}
