import { useMutation, useMutationState, useQueryClient } from "@tanstack/react-query";
import { apiFetch, isConflict, isNotFound } from "../../scan/api/client";
import { invalidateFromGenLayout, invalidateGenJobs, invalidateGenLayout, keys } from "../../scan/api/queries";
import type { Layout } from "../../../shared/api/types";
import { useSession } from "../../../shared/auth/useSession";
import {
  addResource,
  chooseType,
  confirmResource,
  liveCall,
  moveEndpoint,
  refreshPullRequest,
  renameResource,
  resetResource,
  resetVersion,
  saveOtcSettings,
  startGeneration,
  testOtcSettings,
} from "./mock";
import type { OtcSettingsForm } from "./types";

/**
 * Start the preliminary grouping of a service (ADR-0056). The server runs it
 * within the request and answers with the stored layout, which the page shows
 * as it is: the grouping is never computed here (ADR-0073).
 *
 * Two refusals are answers, not failures. A `409` says the service has a
 * layout already - someone else started the grouping (ADR-0072) - so the
 * layout is read again. A `404` says it has left the /generation list, so the
 * list is read again too. The page shows what they say. Anything else is a
 * failure that stored nothing, so the start can simply be repeated (ADR-0061).
 */
export function useStartLayout(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Layout | "taken" | "gone"> => {
      try {
        return await apiFetch<Layout>(`/generation/services/${encodeURIComponent(name)}/layout`, { method: "POST" });
      } catch (error) {
        if (isConflict(error)) return "taken";
        if (isNotFound(error)) return "gone";
        throw error;
      }
    },
    /* The start stays under way until the page has what to show, so the
       button does not come back in between to be clicked again. */
    onSuccess: async (stored) => {
      if (typeof stored === "object") {
        /* The answer is the stored layout: shown as it is, and what it feeds
           read again. A read of the layout still under way may hold an answer
           from before the grouping; it is dropped, so it cannot land on top. */
        await qc.cancelQueries({ queryKey: keys.genLayout(name) });
        qc.setQueryData(keys.genLayout(name), stored);
        await invalidateFromGenLayout(qc, name);
        return;
      }
      if (stored === "taken") {
        await invalidateGenLayout(qc, name);
        return;
      }
      await Promise.all([invalidateGenLayout(qc, name), qc.invalidateQueries({ queryKey: keys.genList() })]);
    },
  });
}

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
    onSettled: () => void invalidateGenLayout(qc, name),
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

/**
 * A generation of the resource on a target, by target id. The job records the
 * signed-in user as who started it, and the mock records when. A refusal comes
 * back as the mutation's error.
 */
export function useStartGeneration(name: string, resource: string) {
  const qc = useQueryClient();
  const { name: by } = useSession();
  return useMutation({
    mutationFn: async (target: string) => startGeneration(name, resource, target, by),
    onSettled: () => invalidateGenJobs(qc, name),
  });
}

/**
 * The state of the pull request of the resource's job on a target, by target
 * id, asked of GitHub now rather than at its next scheduled poll (owner
 * decision). Nothing changes on screen before the mock has answered; the jobs
 * are fetched again either way, and a refusal comes back as the mutation's error.
 */
export function useRefreshPullRequest(name: string, resource: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (target: string) => refreshPullRequest(name, resource, target),
    onSettled: () => invalidateGenJobs(qc, name),
  });
}

/** One live call: the target whose generated SDK makes it, the endpoint, and the path and query values. */
export interface LiveCall {
  target: string;
  endpoint: string;
  path: Record<string, string>;
  query: Record<string, string>;
}

/**
 * A live call of a GET operation of the resource against the OTC tenant. It
 * changes nothing, in the panel or in the tenant, so nothing is fetched again:
 * the answer is the mutation's data, and a refusal its error.
 */
export function useLiveCall(name: string, resource: string) {
  return useMutation({
    mutationFn: async ({ target, endpoint, path, query }: LiveCall) =>
      liveCall(name, resource, target, endpoint, { path, query }),
  });
}

/**
 * The OTC tenant settings, as the form has them; the keys are written, never
 * read back. Nothing changes on screen before the mock has answered, so there
 * is nothing to roll back: a refusal comes back as the mutation's error, and the
 * settings are fetched again either way - before the mutation settles, so the
 * form can drop what was typed without showing the old values in between.
 */
export function useSaveOtcSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (form: OtcSettingsForm) => saveOtcSettings(form),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.otcSettings }),
  });
}

/**
 * A test of the OTC tenant as the form has it. It saves nothing, so nothing is
 * fetched again: how it went is the mutation's data, and a refusal its error.
 */
export function useTestOtcSettings() {
  return useMutation({ mutationFn: async (form: OtcSettingsForm) => testOtcSettings(form) });
}
