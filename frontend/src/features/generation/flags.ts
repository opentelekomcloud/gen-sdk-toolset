/** Per-target state in the Generation list (ADR-0050). TODO(#150): switch on with real generation data. */
export const SHOW_GEN_STATE: boolean = false;

/**
 * The result page of a generation. Off, it shows PageNotFound for any service
 * (ADR-0086): there is no generation on the server yet, and the page would show
 * the in-memory mock's. TODO(#150): switch on with real generation data.
 */
export const SHOW_GEN_RESULT: boolean = false;
