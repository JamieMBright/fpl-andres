import { type ReactNode } from "react";

/**
 * One step of the page, folded away until it is wanted.
 *
 * The plan is long: a snapshot, a record, a fifteen and thirty-eight
 * gameweeks. Shown all at once it reads as a wall, and the reader loses the
 * order the steps are meant to be taken in. Each step is a box, and the ones
 * that matter now are open.
 *
 * A native `details` rather than a button and a state flag: it is
 * keyboard-operable, findable by the browser's own in-page search, and open by
 * default when printed, none of which a hand-rolled toggle gets for free.
 */
export function PlanStep({
  children,
  defaultOpen = false,
  note,
  step,
  title,
}: {
  children: ReactNode;
  defaultOpen?: boolean;
  /** Shown on the closed box, so a reader can skip it without opening it. */
  note?: ReactNode;
  step: string;
  title: string;
}) {
  return (
    <details className="plan-step" open={defaultOpen}>
      <summary className="plan-step-summary">
        <span className="plan-step-index mono">{step}</span>
        <span className="plan-step-title">{title}</span>
        {note === undefined ? null : (
          <span className="plan-step-note mono">{note}</span>
        )}
      </summary>
      <div className="plan-step-body">{children}</div>
    </details>
  );
}
