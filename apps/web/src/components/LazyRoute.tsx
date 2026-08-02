import { Suspense, type PropsWithChildren } from "react";

export function LazyRoute({ children }: PropsWithChildren) {
  return (
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
  );
}
