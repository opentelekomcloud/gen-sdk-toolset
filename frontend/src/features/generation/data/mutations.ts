import { useMutation, useMutationState, useQueryClient } from "@tanstack/react-query";
import { invalidateGenJobs, invalidateGenLayout, keys } from "../../scan/api/queries";
import { useSession } from "../../../shared/auth/useSession";
import {
  addResource,
  chooseType,
  confirmResource,
  moveEndpoint,
  renameResource,
  resetResource,
  resetVersion,
  startGeneration,
} from "./mock";

/** One change to the shared layout of a service, by resource, endpoint and version id. */
export type LayoutEdit =
  | { kind: "rename"; resource: string; name: string }
  | { kind: "move"; endpoint: string; to: string }
  | { kind: "add"; version: string }
  | { kind: "confirm"; resource: string }
  | { kind: "resetResource"; resource: string }
  | { kind: "resetVersion"; version: string };

/**
 * Edits of a service's layout. Nothing changes on screen before the mock has
 * answered, so there is nothing to roll back: a refusal comes back as the
 * mutation's error, and the layout is fetched again either way. A confirmation
 * records the signed-in user; the mock records when (owner decision). The edits
 * are kept for the session, for `useLayoutEdited`.
 */
export function useEditLayout(name: string) {
  const qc = useQueryClient();
  const { name: by } = useSession();
  return useMutation({
    mutationKey: keys.genLayoutEdit(name),
    gcTime: Infinity,
    mutationFn: async (edit: LayoutEdit) => {
      switch (edit.kind) {
        case "rename":
          return renameResource(name, edit.resource, edit.name);
        case "move":
          return moveEndpoint(name, edit.endpoint, edit.to);
        case "add":
          return addResource(name, edit.version);
        case "confirm":
          return confirmResource(name, edit.resource, by);
        case "resetResource":
          return resetResource(name, edit.resource);
        case "resetVersion":
          return resetVersion(name, edit.version);
      }
    },
    onSettled: () => invalidateGenLayout(qc, name),
  });
}

/**
 * Whether an edit of the service's layout went through in this session: the
 * prototype's note, kept per service until the panel reloads - as long as the
 * mock keeps the edits - however often the page is left.
 */
export function useLayoutEdited(name: string) {
  return useMutationState({ filters: { mutationKey: keys.genLayoutEdit(name), exact: true, status: "success" } }).length > 0;
}

/** A field of a resource's class, and the type chosen for its problem; null takes the choice back. */
export interface TypeChoice {
  cls: string;
  field: string;
  type: string | null;
}

/**
 * The type for a field whose type the docs leave open. The choice records the
 * signed-in user, and the mock records when. As with the layout, nothing
 * changes on screen before the mock has answered, and the spec is fetched
 * again either way.
 */
export function useChooseType(name: string, resource: string) {
  const qc = useQueryClient();
  const { name: by } = useSession();
  return useMutation({
    mutationFn: async ({ cls, field, type }: TypeChoice) => chooseType(name, resource, cls, field, type, by),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.genSpec(name, resource) }),
  });
}

/** A generation of the resource on a target, by target id. A refusal comes back as the mutation's error. */
export function useStartGeneration(name: string, resource: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (target: string) => startGeneration(name, resource, target),
    onSettled: () => invalidateGenJobs(qc, name),
  });
}
