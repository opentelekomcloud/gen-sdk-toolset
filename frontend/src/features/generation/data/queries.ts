import { useQuery } from "@tanstack/react-query";
import { keys } from "../../scan/api/queries";
import { generationAttention, generationResources, generationServices, generationSpec, generationTargets } from "./mock";

/** Targets in display order. The first is the default: the one a page works on
 *  when the address names none. */
export function useGenerationTargets() {
  return useQuery({ queryKey: keys.genTargets, queryFn: async () => generationTargets() });
}

/** Every service in Generation, with its state on each target. */
export function useGenerationServices() {
  return useQuery({ queryKey: keys.genServices, queryFn: async () => generationServices() });
}

/** The resources of one service's layout, each with its generation on every target. */
export function useGenerationResources(name: string) {
  return useQuery({ queryKey: keys.genResources(name), queryFn: async () => generationResources(name) });
}

/** What one resource of a service will be generated as: its operations and classes, with the types chosen so far. */
export function useGenerationSpec(name: string, resource: string) {
  return useQuery({ queryKey: keys.genSpec(name, resource), queryFn: async () => generationSpec(name, resource) });
}

/** Generation's rules for the shared attention band - same shape as the scan rules. */
export function useGenerationAttention() {
  return useQuery({ queryKey: keys.genAttention, queryFn: async () => generationAttention() });
}
