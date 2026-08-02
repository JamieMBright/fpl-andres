import { useSyncExternalStore } from "react";

/**
 * Whether the browser believes it has a network.
 *
 * Audit item #120. A dropped connection was rendered as a hard error --
 * "Fantasy Premier League could not be reached" -- which is both wrong and
 * unhelpful: FPL is fine, the train went into a tunnel. Telling someone a
 * remote service is down when their own connection is gone sends them to check
 * the wrong thing.
 *
 * `navigator.onLine` is famously weak: true means "there is an interface with a
 * route", not "the internet works". That is exactly why it is used only to
 * explain a failure that already happened, never to prevent a request. A
 * request is always attempted; if it fails and this says offline, the message
 * changes. False negatives cost nothing, and `false` from this API is reliable
 * even though `true` is not.
 *
 * `useSyncExternalStore` rather than `useState` plus `useEffect`. The naive
 * version has a gap: the value can change between the first render and the
 * effect that subscribes, and neither event fires again to say so. Closing it
 * by calling `setState` inside the effect works, but triggers a cascading
 * render on every mount -- which the lint rule refuses, correctly. This hook
 * exists for exactly this shape of problem, and closes the gap by
 * construction rather than by an extra render.
 */

function subscribe(onChange: () => void): () => void {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

function readOnline(): boolean {
  return navigator.onLine;
}

/**
 * There is no navigator outside a browser, and no network state to report.
 * Claiming online is the right default: it renders nothing, and a banner in
 * prerendered HTML would be a claim about a connection the server cannot see.
 */
function readOnlineOffBrowser(): boolean {
  return true;
}

export function useOnlineStatus(): boolean {
  return useSyncExternalStore(subscribe, readOnline, readOnlineOffBrowser);
}
