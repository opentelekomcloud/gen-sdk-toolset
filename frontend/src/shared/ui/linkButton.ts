/**
 * A router link drawn as a small outline ODSButton. ODSButton cannot be the
 * link itself - its `href` opens a new window - so links that lead somewhere
 * inside the panel stay `<Link>` and borrow the button's shape from the same
 * ODS tokens: pill radius, minimum tappable height, component spacing.
 */
export const linkButtonCls =
  "inline-flex min-h-[var(--sizing-minimum-tappable-area)] shrink-0 items-center gap-2 rounded-full border border-ink px-[var(--spacing-component-6)] text-sm font-bold text-ink transition hover:bg-surface-subtle";
