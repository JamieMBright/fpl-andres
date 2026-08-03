import { Link } from "react-router-dom";

import { deadline as deadlineFormatter } from "../format";

const HORIZONS = [1, 3, 5, 7] as const;

/** What the plan will contain, stated plainly while there is nothing to plan. */
export function TransferPlanPanel({
  firstDeadline,
}: {
  firstDeadline: string | null;
}) {
  const deadline = firstDeadline ? new Date(firstDeadline) : null;
  const formatted =
    deadline && !Number.isNaN(deadline.getTime())
      ? deadlineFormatter.format(deadline)
      : null;

  return (
    <section className="transfer-plan" aria-labelledby="plan-title">
      <div className="dossier-heading dossier-heading-compact">
        <div>
          <p className="eyebrow">Next moves</p>
          <h2 id="plan-title">Your transfer plan</h2>
        </div>
        <span className="mono plan-state">Not yet</span>
      </div>

      <p>
        I will not show you a transfer plan built on nothing. No gameweek of the
        2026/27 season has been played, so every player&rsquo;s form is unknown
        and any ranking I produced today would be invented.
      </p>
      <p>
        What I can do without your squad is plan the season from the opening one
        everybody starts with: <Link to="/plan">gameweek 1 to 38</Link>, every
        eleven, captain and transfer, with the confidence falling away the
        further out it reaches.
      </p>
      {formatted ? (
        <p className="mono plan-deadline">First deadline: {formatted} UTC</p>
      ) : null}

      <h3>What it will show, once there is evidence</h3>
      <ul className="plan-promises">
        <li>
          <strong>
            Expected points at {HORIZONS.join(", +")} gameweeks ahead
          </strong>{" "}
          for every player you own, so a move that wins next Saturday and loses
          the following month is visible as exactly that.
        </li>
        <li>
          <strong>The next few transfers in order</strong>, each with the points
          it gains over the horizon and what it costs — nothing for a banked
          transfer, four points once the bank is empty.
        </li>
        <li>
          <strong>Points per pound</strong>, including whether a premium earns
          his price or whether spreading the same money returns more.
        </li>
        <li>
          <strong>Floor and ceiling</strong>, not just the average. A defender
          hitting the defensive-contribution threshold most weeks is a different
          holding from one chasing clean sheets on the same expectation.
        </li>
        <li>
          <strong>Ownership inside your mini-league</strong>, once a deadline
          has passed and rival picks are legally readable, so you can see which
          of your players actually gain you ground.
        </li>
      </ul>

      <p className="plan-footnote">
        Every one of those is built and tested against seven previous seasons.
        You can check the working on the{" "}
        <a href="/calibration">calibration page</a>, including where the method
        loses.
      </p>
    </section>
  );
}
