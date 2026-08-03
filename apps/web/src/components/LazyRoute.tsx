import { Suspense, type PropsWithChildren } from "react";

import { ErrorBoundary } from "./ErrorBoundary";

export function LazyRoute({ children }: PropsWithChildren) {
  return (
    // Each page arrives as its own file, so each can fail to arrive on its own.
    // Catching it here keeps the rest of the site up and names the failure,
    // rather than handing the router's developer screen to a reader.
    <ErrorBoundary>
      <Suspense
        fallback={
          // Carries its own h1: while the chunk is in flight this is the whole
          // page, and a page without a heading is one a screen reader cannot
          // orient in.
          <section className="text-page" aria-busy="true">
            <p className="eyebrow">Loading</p>
            <h1 tabIndex={-1}>Fetching this page.</h1>
          </section>
        }
      >
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}
