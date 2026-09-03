import { useAuth } from "react-oidc-context";
import { canWrite, rolesFromToken, type PanelRole } from "./roles";

export interface PanelSession {
  /** The login the backend will record for anything this session does. */
  name: string;
  roles: PanelRole[];
  /** Whether to offer the controls that change panel state. */
  canWrite: boolean;
  signOut: () => void;
}

/**
 * Who is signed in, in the panel's own terms.
 *
 * The roles come from the access token because that is the token the backend
 * reads them from - taking them from the ID token instead would let the two
 * disagree about what a session may do. It is decoded, not verified: see
 * `roles.ts` for why that is safe.
 */
export function useSession(): PanelSession {
  const auth = useAuth();
  const roles = rolesFromToken(auth.user?.access_token);
  return {
    name:
      auth.user?.profile.preferred_username ??
      auth.user?.profile.name ??
      auth.user?.profile.email ??
      auth.user?.profile.sub ??
      "",
    roles,
    canWrite: canWrite(roles),
    signOut: () => void auth.signoutRedirect(),
  };
}
