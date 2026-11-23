/** Per-target state in the Generation list (ADR-0050). TODO(#150): switch on with real generation data. */
export const SHOW_GEN_STATE: boolean = false;

/**
 * The result page of a generation. Off, it shows PageNotFound for any service
 * (ADR-0086): there is no generation on the server yet, and the page would show
 * the in-memory mock's. TODO(#150): switch on with real generation data.
 */
export const SHOW_GEN_RESULT: boolean = false;

/**
 * What the pages show of generation itself. On the service page: each target's
 * merged resources and progress bar, the target it is built on, the repository
 * its pull requests go to, and each resource's job or Generate link. Off, the
 * page shows the repo, the way to its layout, the choice of target with Ansible
 * modules not connected yet, and what the stored layout allows in its centre
 * (ISS-0038, ISS-0039, ISS-0041). In the layout editor: each resource's job
 * pill, the lock of one generating or in review, and the hiding of one merged
 * on every connected target (ISS-0042). The server has no generation data yet.
 * TODO(#150): switch on with real generation data.
 */
export const SHOW_GEN_JOBS: boolean = false;

/**
 * Where a resource of the layout editor came from: `auto`, from the
 * preliminary grouping, or `new`, added by hand (ISS-0042). The stored layout
 * does not say, so off, a resource shows only whether it is confirmed.
 * TODO: switch on once the layout read says where a resource came from.
 */
export const SHOW_LAYOUT_ORIGIN: boolean = false;
