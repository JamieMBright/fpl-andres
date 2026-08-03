import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/** A chunk that will not load is almost always a deploy, not a bug. */
function isChunkFailure(error: Error): boolean {
  return (
    error.name === "ChunkLoadError" ||
    /dynamically imported module|Importing a module script failed|Failed to fetch/i.test(
      error.message,
    )
  );
}

/**
 * A render-time throw anywhere in the tree used to blank the whole page.
 *
 * React unmounts the entire tree when nothing catches, so a single bad field in
 * one panel took the site with it. This keeps the failure visible and the page
 * usable, and says plainly that nothing was invented to fill the gap.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(
      JSON.stringify({
        level: "error",
        event: "render_failure",
        message: error.message,
        stack: error.stack ?? null,
        componentStack: info.componentStack ?? null,
      }),
    );
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    // A page is fetched on demand as its own file. A deploy replaces those
    // files, so a tab left open across one asks for a name that no longer
    // exists. Nothing is wrong with the code and a reload fixes it.
    const stale = isChunkFailure(error);

    return (
      <main className="text-page" id="main">
        <p className="eyebrow">{stale ? "Out of date" : "Something broke"}</p>
        <h1>
          {stale
            ? "This page changed while you had it open."
            : "I could not draw this page."}
        </h1>
        <p>
          {stale
            ? "The copy of the site in this tab is asking for a file that has since been replaced. Nothing is broken and nothing has been lost \u2014 the tab needs to fetch the new one."
            : "A fault in my own code stopped this page rendering. I have not shown you a half-built version of it, because a partial answer here is worse than none: you could not tell which parts were real."}
        </p>

        <p className="error-detail mono">
          <span className="error-detail-kind">{error.name}</span>
          {error.message}
        </p>

        <p className="error-actions">
          <button
            className="error-reload"
            onClick={() => {
              window.location.reload();
            }}
            type="button"
          >
            Reload the page
          </button>
          <a className="mono" href="/">
            Back to the start
          </a>
        </p>

        {stale ? null : <p>The full stack is in the browser console.</p>}
      </main>
    );
  }
}
