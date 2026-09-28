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
