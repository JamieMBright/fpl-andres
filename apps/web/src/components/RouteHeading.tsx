import { useEffect, useRef, type PropsWithChildren } from "react";
import { useNavigationType } from "react-router-dom";

/**
 * The route heading, which takes focus when you navigate to a new page.
 *
 * It focuses itself rather than the frame hunting for `main h1` after a
 * navigation, because a code-split route is not in the document yet when the
 * navigation happens - the Suspense fallback is.
 *
 * Keyed on the navigation type, not on mounting: React remounts under
 * StrictMode, and a first paint must not drag focus away from where the browser
 * put it. Only a PUSH is the user asking to go somewhere.
 */
export function RouteHeading({
  children,
  translate,
}: PropsWithChildren<{ translate?: "yes" | "no" }>) {
  const heading = useRef<HTMLHeadingElement>(null);
  const navigationType = useNavigationType();

  useEffect(() => {
    if (navigationType !== "PUSH" && navigationType !== "REPLACE") {
      return;
    }
    heading.current?.focus();
  }, [navigationType]);

  return (
    <h1 ref={heading} tabIndex={-1} translate={translate}>
      {children}
    </h1>
  );
}
