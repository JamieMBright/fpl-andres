import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { failed: boolean };

/**
 * A render-time throw anywhere in the tree used to blank the whole page.
 *
 * React unmounts the entire tree when nothing catches, so a single bad field in
 * one panel took the site with it. This keeps the failure visible and the page
 * usable, and says plainly that nothing was invented to fill the gap.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
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
    if (!this.state.failed) {
      return this.props.children;
    }
    return (
      <main className="text-page" id="main">
        <p className="eyebrow">Something broke</p>
        <h1>I could not draw this page.</h1>
        <p>
          A fault in my own code stopped this page rendering. I have not shown
          you a half-built version of it, because a partial answer here is worse
          than none: you could not tell which parts were real.
        </p>
        <p>
          Reloading may work if it was a one-off. If it happens again, the
          detail is in the browser console.
        </p>
        <p>
          <a className="mono" href="/">
            Back to the start
          </a>
        </p>
      </main>
    );
  }
}
