import { useQuery } from "@tanstack/react-query";
import { apiFetch, qs } from "../../scan/api/client";
import { blockOf, keys, retryJoining } from "../../scan/api/queries";
import type { GenerationServiceItem, Layout } from "../../../shared/api/types";
import {
  generationAttention,
  generationResources,
  generationServices,
  generationSpec,
  generationTargets,
  otcSettings,
} from "./mock";

/** Targets in display order. The first is the default: the one a page works on
 *  when the address names none. */
export function useGenerationTargets() {
  return useQuery({ queryKey: keys.genTargets, queryFn: async () => generationTargets() });
}

/** Every service in Generation, with its state on each target. */
export function useGenerationServices() {
  return useQuery({ queryKey: keys.genServices, queryFn: async () => generationServices() });
}

export function useGenerationList(params: { q: string }) {
  return useQuery({
    queryKey: keys.genList(params),
    queryFn: () => apiFetch<GenerationServiceItem[]>(`/generation/services${qs({ ...params })}`),
    /* Keep the table while a new search loads - but never from a request that
       failed: its rows are the stale list the error block is standing in for. */
    placeholderData: (prev, prevQuery) => (prevQuery?.state.status === "error" ? undefined : prev),
  });
}

/**
 * Whether the pages of a service open: the service page and the layout page do
 * for a service in the /generation list, and show PageNotFound for any other
 * (ADR-0086, ADR-0087). The list is the server's, without the search: which
 * services are in Generation is decided there, and is not decided again here
 * (ADR-0049).
 *
 * The list is the block these pages stand on, so it follows its rule
 * (ADR-0081): a request that failed, on the first load or on a refresh, is a
 * failure with a Retry - never PageNotFound, and never the answer before it.
 * A service that left the list - excluded, or out of it since its active
 * snapshot changed - turns into PageNotFound with the refresh that says so.
 */
export function useInGeneration(name: string) {
  const list = useGenerationList({ q: "" });
  const { data, failed, pending } = blockOf(list);
  return {
    listed: data?.some((s) => s.name === name) ?? false,
    failed,
    pending,
    /* The list itself, for a `BlockFailed` warning, which runs its own Retry. */
    query: list,
    retry: () => void retryJoining(list),
  };
}

/**
 * The layout of one service, read from the backend; `has_layout` is false until
 * its grouping has run. `enabled: false` holds it back - for a repo off the
 * /generation list, which the backend answers 404.
 */
export function useGenerationLayout(name: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: keys.genLayout(name),
    queryFn: () => apiFetch<Layout>(`/generation/services/${encodeURIComponent(name)}/layout`),
    enabled,
  });
}

/**
 * The resources of one service's layout, each with its generation on every
 * target. `enabled: false` holds them back, for a service with no layout.
 */
export function useGenerationResources(name: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({ queryKey: keys.genResources(name), queryFn: async () => generationResources(name), enabled });
}

/** What one resource of a service will be generated as: its operations and classes, with the types chosen so far. */
export function useGenerationSpec(name: string, resource: string) {
  return useQuery({ queryKey: keys.genSpec(name, resource), queryFn: async () => generationSpec(name, resource) });
}

/** Generation's rules for the shared attention band - same shape as the scan rules. */
export function useGenerationAttention() {
  return useQuery({ queryKey: keys.genAttention, queryFn: async () => generationAttention() });
}

/** The OTC tenant the panel's live calls go to; of its keys, only whether each is stored. */
export function useOtcSettings() {
  return useQuery({ queryKey: keys.otcSettings, queryFn: async () => otcSettings() });
}
