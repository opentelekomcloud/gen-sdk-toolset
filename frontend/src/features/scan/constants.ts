import type { Section } from "./types";
import type { MessageKey } from "../../shared/i18n";

/** The 7 sections in fixed order (PS1). */
export const SECTIONS: readonly Section[] = [
  "path_params",
  "query_params",
  "headers",
  "body",
  "response",
  "example_request",
  "example_response",
] as const;

/** i18n key for a section label (dictionaries hold section.* entries).
 *  Takes the wire value: `SectionDetail.name` is `str` in the schema, and the
 *  seven names above are what the scanner can actually put there. */
export const sectionLabelKey = (s: string): MessageKey => `section.${s}` as MessageKey;

/**
 * The bucket the API uses for documents that name no API version. It is the
 * same key the snapshot analytics writes, so the chip, the counts and the
 * stored roll-up can never mean different things.
 */
export const UNVERSIONED = "unversioned";
