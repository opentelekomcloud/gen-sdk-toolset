import { onlineManager, QueryCache, QueryClient, type Query } from "@tanstack/react-query";

/**
 * How often every mounted query is fetched again from the server (ADR-0076).
 *
 * A visible tab has to show a change no later than 15 s after it is saved on
 * the server (ADR-0077); the 5 s left over cover the response time, which is
 * longest for summary and attention - both recompute every service.
 */
export const REFETCH_INTERVAL_MS = 10_000;

/** How many times the tab has been shown again after being hidden. */
let returns = 0;
/** For each query, how many returns there had been when its last answer came. */
const answeredAfter = new WeakMap<object, number>();

/**
 * Lets queries fetch only while the tab is visible, as well as online (ADR-0080).
 *
 * TanStack Query holds back the periodic refetch and the retries of a hidden
 * tab by itself, but a fetch started by an invalidation or by a query mounted
 * while hidden waits only for the network. Its online state is the one thing
 * every fetch waits for, so a hidden tab counts as offline here: the fetch is
 * paused, sends nothing, and goes out when the tab is shown again.
 *
 * The network part is TanStack's own default: only the `online` and `offline`
 * events move it, never `navigator.onLine`, which reports offline wrongly in
 * some browsers.
 *
 * Mutations wait on the same state, so one started in a hidden tab would go
 * out once the tab is shown. Every mutation in the panel starts from a click,
 * which a hidden tab cannot receive; one sent before the tab was hidden is not
 * held back.
 *
 * A return is counted before the tab is allowed to fetch, so the refetch that
 * follows can tell a return from a network coming back. Counted, not timed: a
 * clock would mistake an answer from the same millisecond as the return for
 * one fetched after it.
 */
function fetchOnlyWhileVisible() {
  onlineManager.setEventListener((setOnline) => {
    let online = true;
    let hidden = document.visibilityState === "hidden";
    const update = () => setOnline(online && !hidden);
    const onVisibility = () => {
      const wasHidden = hidden;
      hidden = document.visibilityState === "hidden";
      // only a change from hidden is a return; a "visible" repeated is none
      if (wasHidden && !hidden) returns += 1;
      update();
    };
    const goOnline = () => {
      online = true;
      update();
    };
    const goOffline = () => {
      online = false;
      update();
    };
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    document.addEventListener("visibilitychange", onVisibility);
    update();
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  });
}

/**
 * The query client the panel runs with.
 *
 * `refetchInterval` is a default rather than a per-hook option, so it applies
 * only to what is on screen: TanStack Query polls mounted queries only. The
 * Header and the Attention Band are mounted on every page, so they refresh
 * everywhere; a page that is not open is not fetched (ADR-0078).
 *
 * `gcTime: 0` drops a query's cache as soon as nothing shows it, so a page
 * opened again loads from the server instead of showing the previous visit
 * (ADR-0078).
 *
 * A hidden tab sends no request at all (`fetchOnlyWhileVisible`). Shown again,
 * it can fetch again, and `refetchOnReconnect` fetches every query on screen at
 * once, however briefly it was hidden, with no threshold. The fetch restarts the
 * interval, so the tab then refreshes like any visible one (ADR-0080). A scan
 * or another user's change made meanwhile reaches it this way, not through a
 * job poll (ADR-0085). A network coming back while the tab stayed visible keeps
 * TanStack's own rule and refetches only data older than `staleTime`: the
 * interval was already keeping the rest current.
 *
 * That is the one trigger of the return: `refetchOnWindowFocus` is off, as
 * TanStack's "focus" is the same visibility change. Focusing a window whose
 * tab stayed visible therefore fetches nothing either: that tab is already on
 * the interval. A request already sent when the tab is hidden is left to
 * finish and its answer is shown; only what would follow it - a retry, a
 * refetch - waits.
 */
export function createQueryClient() {
  fetchOnlyWhileVisible();
  return new QueryClient({
    queryCache: new QueryCache({ onSuccess: (_data, query) => answeredAfter.set(query, returns) }),
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        retry: 1,
        refetchInterval: REFETCH_INTERVAL_MS,
        refetchOnReconnect: refetchOnReturn,
        refetchOnWindowFocus: false,
        gcTime: 0,
      },
    },
  });
}

/**
 * Every query on screen when the tab is shown again; otherwise, as TanStack
 * does by default, only the stale ones. A query whose last answer came before
 * the latest return has not been fetched since the tab came back - including
 * one that answered while the tab was hidden, or never answered. After a
 * network outage alone, every query on screen has answered since.
 */
function refetchOnReturn(query: Query): boolean | "always" {
  return (answeredAfter.get(query) ?? -1) < returns ? "always" : true;
}
