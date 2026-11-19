/** Per-target state in the Generation list (ADR-0050). TODO(#150): switch on with real generation data. */
export const SHOW_GEN_STATE: boolean = false;

/**
 * The result page of a generation. Off, it shows PageNotFound for any service
 * (ADR-0086): there is no generation on the server yet, and the page would show
 * the in-memory mock's. TODO(#150): switch on with real generation data.
 */
export const SHOW_GEN_RESULT: boolean = false;

/**
 * What the service page shows of generation itself: each target's merged
 * resources and progress bar, the target it is built on, the repository its
 * pull requests go to, and each resource's job or Generate link. Off, the page
 * shows the repo, the way to its layout, the choice of target with Ansible
 * modules not connected yet, and what the stored layout allows in its centre
 * (ISS-0038, ISS-0039, ISS-0041); the server has no generation data yet.
 * TODO(#150): switch on with real generation data.
 */
export const SHOW_GEN_JOBS: boolean = false;
