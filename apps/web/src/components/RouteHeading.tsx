import { useEffect, useRef, type PropsWithChildren } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

/**
 * The route heading, which takes focus when you navigate to a new page.
 *
 * It focuses itself rather than the frame hunting for `main h1` after a
 * navigation, because a code-split route is not in the document yet when the
 * navigation happens - the Suspense fallback is.
 *
 * Keyed on the path, not on the history entry. Every control that writes its
 * state to the query string pushes an entry, so a legend click or a slider
 * counted as "the user asking to go somewhere" and yanked the page back to the
 * top. A page you are still reading is not a page you navigated to.
 *
 * A first paint never steals focus either: the browser has already put it
 * somewhere, and React remounts under StrictMode.
 */
/**
 * The path this app last settled on.
 *
 * Module scope, not a ref: every route renders its own `RouteHeading`, so a
 * per-instance memory is always empty on arrival and would never fire. It also
 * has to survive the remount StrictMode performs.
 */
let lastPath: string | null = null;

export function RouteHeading({
  children,
  translate,
}: PropsWithChildren<{ translate?: "yes" | "no" }>) {
  const heading = useRef<HTMLHeadingElement>(null);
  const navigationType = useNavigationType();
  const { pathname } = useLocation();

  useEffect(() => {
    const arrived = lastPath !== null && lastPath !== pathname;
    lastPath = pathname;
    if (!arrived) return;
    if (navigationType !== "PUSH" && navigationType !== "REPLACE") {
      return;
    }
    heading.current?.focus();
  }, [navigationType, pathname]);

  return (
    <h1 ref={heading} tabIndex={-1} translate={translate}>
      {children}
    </h1>
  );
}
