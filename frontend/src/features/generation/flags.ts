/**
 * Parts of the Generation pages that are built but switched off until the
 * backend has the data for them.
 */

/** The list's per-target state: target columns, state chips and the `?filter`
 *  they drive. Services selected from Scan data have no per-target state yet,
 *  so the list shows names only (ADR-0050) - TODO(#150): switch on once real
 *  generation data is connected. */
export const SHOW_GEN_STATE: boolean = false;
