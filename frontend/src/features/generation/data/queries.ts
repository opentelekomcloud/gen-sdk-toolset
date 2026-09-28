import { useQuery } from "@tanstack/react-query";
import { keys } from "../../scan/api/queries";
import { generationAttention, generationServices, generationTargets } from "./mock";

/** Targets in display order. The first is the default: the one a page works on
 *  when the address names none. */
export function useGenerationTargets() {
  return useQuery({ queryKey: keys.genTargets, queryFn: async () => generationTargets() });
}

/** Every service in Generation, with its state on each target. */
export function useGenerationServices() {
  return useQuery({ queryKey: keys.genServices, queryFn: async () => generationServices() });
}

/** Generation's rules for the shared attention band - same shape as the scan rules. */
export function useGenerationAttention() {
  return useQuery({ queryKey: keys.genAttention, queryFn: async () => generationAttention() });
}
