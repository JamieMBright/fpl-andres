import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { tally, type ScoredCall } from "../state/scorecard";

/**
 * What I said, and what you did.
 *
 * A recommendation nobody checks is an opinion. Every settled week is a call
 * made before the deadline against the squad FPL published afterwards, and the
 * point of showing it is that it can say I was wrong.
 *
 * Agreement, not points. Scoring one captain against another needs each
 * player's points for the gameweek, and no endpoint this app is allowed to call
 * publishes them. Counting agreement is a smaller claim that is true.
 */

function nameOf(elementId: number | null): string {
  if (elementId === null) return "no move";
  return PLAYERS_BY_ELEMENT_ID.get(elementId)?.name ?? `#${String(elementId)}`;
}

function moveOf(out: number | null, into: number | null): string {
  if (out === null || into === null) return "No transfer";
  return `${nameOf(out)} \u2192 ${nameOf(into)}`;
}

export function Scorecard({ calls }: { calls: readonly ScoredCall[] }) {
  const settled = calls.filter((call) => call.settled !== null);
  if (settled.length === 0) return null;

  const counted = tally(settled);

  return (
    <section className="scorecard" aria-labelledby="scorecard-title">
      <div className="dossier-heading dossier-heading-compact">
        <div>
          <p className="eyebrow">Kept honest</p>
          <h2 id="scorecard-title">What I said, and what you did</h2>
        </div>
        <span className="mono">
          {counted.captainAgreed}/{counted.settled} captains
        </span>
      </div>

      <p className="scorecard-lede">
        Each call was recorded before its deadline and never rewritten
        afterwards. Agreement only: scoring one captain against another needs
        every player&rsquo;s points for the gameweek, and nothing this site is
        allowed to read publishes them.
      </p>

      <div
        aria-label="What I said and what you did. Scrollable table."
        className="squad-table-wrap"
        role="region"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
      >
        <table className="scorecard-table">
          <thead>
            <tr>
              <th scope="col">GW</th>
              <th scope="col">I said</th>
              <th scope="col">You did</th>
              <th scope="col">Captain</th>
            </tr>
          </thead>
          <tbody>
            {settled.map((call) => {
              const agreedCaptain = call.settled?.captain === call.captain;
              const agreedMove =
                call.settled?.elementIn === call.elementIn &&
                call.settled.elementOut === call.elementOut;
              return (
                <tr key={call.event}>
                  <td className="mono">{call.event}</td>
                  <td>{moveOf(call.elementOut, call.elementIn)}</td>
                  <td className={agreedMove ? "scorecard-agreed" : undefined}>
                    {moveOf(
                      call.settled?.elementOut ?? null,
                      call.settled?.elementIn ?? null,
                    )}
                  </td>
                  <td
                    className={agreedCaptain ? "scorecard-agreed" : undefined}
                  >
                    {agreedCaptain
                      ? nameOf(call.captain)
                      : `${nameOf(call.captain)} \u00b7 you had ${nameOf(
                          call.settled?.captain ?? null,
                        )}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
