/**
 * A text field in the ODS look. ODS 3.0.1 ships no plain input component - its
 * one text field, ODSInlineSearch, is an autocomplete that owns its value and
 * opens a result list - so the panel's own inputs keep native elements and
 * take the ODS shape and tokens from here.
 */
export const fieldCls =
  "h-10 rounded-lg border border-neutral-400 bg-surface px-3 text-sm text-ink outline-none transition placeholder:text-neutral-600 hover:border-neutral-700 focus:border-ink";
