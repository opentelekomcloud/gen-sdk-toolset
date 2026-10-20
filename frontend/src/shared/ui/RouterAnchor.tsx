import { forwardRef, type AnchorHTMLAttributes } from "react";
import { Link } from "react-router";

type Props = AnchorHTMLAttributes<HTMLAnchorElement> & { "data-state"?: unknown };

/**
 * The anchor an ODS link renders, as a router link: `<ODSLink Component={RouterAnchor} href="/scan">`
 * navigates inside the app instead of reloading it. ODS types its links as
 * plain anchors, so the target travels as `href`, and router state - which no
 * anchor attribute can carry - as `data-state`.
 */
export const RouterAnchor = forwardRef<HTMLAnchorElement, Props>(({ href = "", "data-state": state, ...rest }, ref) => (
  <Link ref={ref} to={href} state={state} {...rest} />
));
RouterAnchor.displayName = "RouterAnchor";
