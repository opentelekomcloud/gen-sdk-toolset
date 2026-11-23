import { useMutation, useMutationState, useQueryClient } from "@tanstack/react-query";
import { apiFetch, isConflict, isNotFound } from "../../scan/api/client";
import { invalidateGenJobs, invalidateGenLayout, keys, showGenLayout } from "../../scan/api/queries";
import type {
  AddResourceRequest,
  Layout,
  MoveEndpointRequest,
  RenameResourceRequest,
} from "../../../shared/api/types";
import { useSession } from "../../../shared/auth/useSession";
import { chooseType, liveCall, refreshPullRequest, saveOtcSettings, startGeneration, testOtcSettings } from "./mock";
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
 *
 * The repo goes in with `mutate(repo)` and comes back with the answer: a page
 * reused for another service while the start is under way hands this mutation
 * its new options, so a name taken from them could file one service's layout
 * under another's.
 */
export function useStartLayout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (repo: string): Promise<Layout | "taken" | "gone"> => {
      try {
        return await apiFetch<Layout>(`/generation/services/${encodeURIComponent(repo)}/layout`, { method: "POST" });
      } catch (error) {
        if (isConflict(error)) return "taken";
        if (isNotFound(error)) return "gone";
        throw error;
      }
    },
    /* The start stays under way until the page has what to show, so the
       button does not come back in between to be clicked again. */
    onSuccess: async (stored, repo) => {
      if (typeof stored === "object") {
        await showGenLayout(qc, repo, stored);
        return;
      }
      if (stored === "taken") {
        await invalidateGenLayout(qc, repo);
        return;
      }
      await Promise.all([invalidateGenLayout(qc, repo), qc.invalidateQueries({ queryKey: keys.genList() })]);
    },
  });
}

/**
 * One of the edits the server takes (ADR-0064): a resource is named by its
 * `id`, which a rename keeps, and an endpoint by its document `path`. There is
 * no delete, and nothing sends an endpoint back to "unassigned" or "no version".
 */
export type LayoutEdit =
  | { kind: "add"; version: string; name: string }
  | { kind: "rename"; resource: number; name: string }
  | { kind: "move"; path: string; to: number };

/** The request of an edit: where it goes, and what it sends. */
function editRequest(repo: string, edit: LayoutEdit): { path: string; body: unknown } {
  const layout = `/generation/services/${encodeURIComponent(repo)}/layout`;
  switch (edit.kind) {
    case "add":
      return {
        path: `${layout}/resources`,
        body: { api_version: edit.version, name: edit.name } satisfies AddResourceRequest,
      };
    case "rename":
      return { path: `${layout}/resources/${edit.resource}/rename`, body: { name: edit.name } satisfies RenameResourceRequest };
    case "move":
      return {
        path: `${layout}/endpoints/move`,
        body: { path: edit.path, resource_id: edit.to } satisfies MoveEndpointRequest,
      };
  }
}

/**
 * Edits of a service's stored layout, each answered with the whole layout.
 * Nothing changes on screen before the server has answered, so there is
 * nothing to roll back. The answer is shown as it is, and what the layout feeds
 * is read again. A refusal leaves the layout unchanged on the server and comes
 * back as the mutation's error; it says the page may be behind - a name taken
 * meanwhile, a resource or an endpoint gone - so the layout is read again too.
 * The caller sends one edit at a time, while none is under way: the answers of
 * two at once could arrive out of order, the older shown over the newer.
 *
 * The repo goes in with `mutate`, and the answer is filed under it rather than
 * under the hook's `name`: a page reused for another service while an edit is
 * under way must not file one service's layout under another's. The edits that
 * went through are kept for the session, for `useLayoutEdited`.
 */
export function useEditLayout(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: keys.genLayoutEdit(name),
    gcTime: Infinity,
    /* The answer goes to the layout's cache here, not into the mutation's
       data: an edit is kept for the session, and keeps no copy of a layout. */
    mutationFn: async ({ repo, edit }: { repo: string; edit: LayoutEdit }): Promise<void> => {
      const { path, body } = editRequest(repo, edit);
      await showGenLayout(qc, repo, await apiFetch<Layout>(path, { method: "POST", body: JSON.stringify(body) }));
    },
    /* Not awaited: the refusal is the page's to show now, not once the layout
       has been read again - a slow read would hold it back and keep the edit
       under way. */
    onError: (_error, { repo }) => {
      void invalidateGenLayout(qc, repo);
    },
  });
}

/**
 * Whether an edit of the service's layout went through in this session: the
 * prototype's note, kept per service until the panel reloads, however often
 * the page is left.
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
