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
 * Navigation state of a card opened from the list: the list's query, so the way
 * back returns to the chip the card was opened on - the prototype's `backToGen`
 * keeps `genChip`. The card's own address does not carry it.
 */
export interface FromList {
  listSearch: string;
}

/** The list a card leads back to: as it was left, or unfiltered when the card was opened some other way. */
export const listPath = (state: Partial<FromList> | null) => `/generation${state?.listSearch ?? ""}`;
