import type { GenTarget } from "../data/types";

/**
 * Address of a Generation page of one service: its card, or `rest` below it
 * (`layout`, `spec/v1/v1_invoices`). The target rides along in the address; the
 * default target is left out, so a card opens as plain `/generation/<name>`.
 */
export const servicePath = (name: string, target: GenTarget, defaultTarget: GenTarget, rest: string[] = []) =>
  `/${["generation", name, ...rest].map(encodeURIComponent).join("/")}${
    target.id === defaultTarget.id ? "" : `?target=${target.id}`
  }`;

/**
 * Navigation state of a card opened from the list: the list's query and its
 * search text, so the way back returns to the list as it was left - the
 * prototype's `backToGen` keeps `genChip` and `genQuery`. The card's own address
 * does not carry them, and the search text is not in the list's address either;
 * the way back hands this state to the list, which takes the search text from it.
 */
export interface FromList {
  listSearch: string;
  listQuery: string;
}

/** The list a card leads back to: as it was left, or unfiltered when the card was opened some other way. */
export const listPath = (state: Partial<FromList> | null) => `/generation${state?.listSearch ?? ""}`;

/**
 * Navigation state of a result opened from its resource's spec: the list's
 * state, and the mark that the way back leads to the spec - the prototype keeps
 * the spec open under the result it started, and names the way back after it.
 */
export interface FromSpec extends Partial<FromList> {
  fromSpec: true;
}
