import { useMutation, useQueryClient } from "@tanstack/react-query";
import { invalidateGenLayout } from "../../scan/api/queries";
import { useSession } from "../../../shared/auth/useSession";
import { addResource, confirmResource, moveEndpoint, renameResource, resetResource, resetVersion } from "./mock";

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
 * records the signed-in user; the mock records when (owner decision).
 */
export function useEditLayout(name: string) {
  const qc = useQueryClient();
  const { name: by } = useSession();
  return useMutation({
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
