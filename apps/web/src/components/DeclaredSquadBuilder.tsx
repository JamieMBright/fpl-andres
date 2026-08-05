import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { money } from "../format";
import {
  forgetDeclaredSquad,
  readDeclaredSquad,
  saveDeclaredSquad,
  SQUAD_BUDGET_TENTHS,
  validateDeclaredSquad,
  type SquadValidation,
} from "../state/declared-squad";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";

/**
 * Build the fifteen you are actually starting the season with.
 *
 * Before the first deadline FPL publishes nothing, so a Team ID alone can only
 * say who you are. Rather than stop at that, this takes your own fifteen,
 * checks it against the published rules, and — once it is legal — treats it as
 * locked in for gameweek one, which is what the season plan then solves from.
 *
 * It is the same mechanism as declaring a transfer FPL has not published yet:
 * your claim, kept in your own browser, labelled as yours rather than observed.
 */

const SLOTS = [
  { position: "GKP", count: 2, label: "Goalkeepers", offset: 0 },
  { position: "DEF", count: 5, label: "Defenders", offset: 2 },
  { position: "MID", count: 5, label: "Midfielders", offset: 7 },
  { position: "FWD", count: 3, label: "Forwards", offset: 12 },
] as const;

function pounds(tenths: number): string {
  return `${money.format(tenths / 10)}m`;
}

function declaredSquadAnnouncement(
  chosenCount: number,
  saved: boolean,
  validation: SquadValidation | null,
): string {
  if (validation === null) {
    return `${String(chosenCount)} of 15 picked.`;
  }
  if (validation.valid) {
    return saved
      ? "Squad locked in for gameweek 1."
      : "Squad is legal and ready to lock in.";
  }
  return `Squad has ${String(validation.problems.length)} problem${validation.problems.length === 1 ? "" : "s"}.`;
}

export function DeclaredSquadBuilder({
  entryId,
  event = 1,
}: {
  entryId: number;
  event?: number;
}) {
  const players = useMemo(
    () =>
      [...PLAYERS_BY_ELEMENT_ID.values()].sort((left, right) =>
        left.name.localeCompare(right.name),
      ),
    [],
  );

  const stored = useMemo(
    () => readDeclaredSquad(window.localStorage, entryId, event),
    [entryId, event],
  );
  const [picks, setPicks] = useState<string[]>(() =>
    stored
      ? stored.elementIds.map(String)
      : Array.from({ length: 15 }, () => ""),
  );
  const [saved, setSaved] = useState(stored !== null);

  const chosen = picks
    .map((pick) => Number(pick))
    .filter((elementId) => Number.isInteger(elementId) && elementId > 0);
  const complete = chosen.length === 15;
  const validation: SquadValidation | null = complete
    ? validateDeclaredSquad(chosen)
    : null;

  const spentTenths = chosen.reduce(
    (total, elementId) =>
      total + (PLAYERS_BY_ELEMENT_ID.get(elementId)?.priceTenths ?? 0),
    0,
  );

  const setSlot = (index: number, value: string) => {
    setPicks((current) => {
      const next = [...current];
      next[index] = value;
      return next;
    });
    setSaved(false);
  };

  const lockIn = () => {
    if (!validation?.valid) return;
    saveDeclaredSquad(window.localStorage, entryId, event, chosen);
    setSaved(true);
  };

  const clear = () => {
    forgetDeclaredSquad(window.localStorage, entryId, event);
    setPicks(Array.from({ length: 15 }, () => ""));
    setSaved(false);
  };

  return (
    <section className="declared-squad" aria-labelledby="declared-squad-title">
      <div className="dossier-heading dossier-heading-compact">
        <div>
          <p className="eyebrow">Your claim, not FPL&rsquo;s record</p>
          <h2 id="declared-squad-title">Build your gameweek 1 fifteen</h2>
        </div>
        <span className="mono">
          {pounds(spentTenths)} of {pounds(SQUAD_BUDGET_TENTHS)}
        </span>
      </div>

      <p>
        FPL keeps every squad private until the first deadline passes, so there
        is nothing public to read for your team yet. Tell me the fifteen you
        have picked and I will hold it as though it were played in gameweek one,
        then plan the remaining thirty-seven around it. It stays in this
        browser.
      </p>

      <form
        className="declared-squad-form"
        onSubmit={(submitted) => {
          submitted.preventDefault();
          lockIn();
        }}
      >
        {SLOTS.map((group) => (
          <fieldset key={group.position}>
            <legend>
              {group.label} ({group.count})
            </legend>
            {Array.from({ length: group.count }, (_unused, offset) => {
              const index = group.offset + offset;
              return (
                <div className="declared-squad-slot" key={index}>
                  <label htmlFor={`squad-slot-${String(index)}`}>
                    {group.position} {String(index + 1)}
                  </label>
                  <select
                    id={`squad-slot-${String(index)}`}
                    onChange={(changed) => {
                      setSlot(index, changed.target.value);
                    }}
                    value={picks[index] ?? ""}
                  >
                    <option value="">Pick a player</option>
                    {players
                      .filter((player) => player.position === group.position)
                      .map((player) => (
                        <option key={player.id} value={player.id}>
                          {player.name} ({player.club},{" "}
                          {pounds(player.priceTenths)})
                        </option>
                      ))}
                  </select>
                </div>
              );
            })}
          </fieldset>
        ))}

        <div className="declared-squad-actions">
          <button
            className="primary-command"
            disabled={validation?.valid !== true}
            type="submit"
          >
            Lock this in for gameweek 1
          </button>
          <button className="secondary-command" onClick={clear} type="button">
            Clear
          </button>
        </div>
      </form>

      <p aria-live="polite" className="visually-hidden" role="status">
        {declaredSquadAnnouncement(chosen.length, saved, validation)}
      </p>
      <div className="declared-squad-report">
        {validation === null ? (
          <p>
            {String(chosen.length)} of 15 picked. Nothing is stored, and no
            squad is assumed for you, until all fifteen obey the rules.
          </p>
        ) : validation.valid ? (
          <>
            <dl className="record-summary">
              <div>
                <dt>Spent</dt>
                <dd className="mono">
                  {pounds(validation.summary.spentTenths)}
                </dd>
              </div>
              <div>
                <dt>In the bank</dt>
                <dd className="mono">
                  {pounds(validation.summary.bankTenths)}
                </dd>
              </div>
              <div>
                <dt>Best eleven, on last season&rsquo;s record</dt>
                <dd className="mono">
                  {validation.summary.bestElevenPoints.toFixed(1)} pts a match
                </dd>
              </div>
              <div>
                <dt>Most from one club</dt>
                <dd className="mono">
                  {validation.summary.clubCounts[0]
                    ? `${String(validation.summary.clubCounts[0].count)} ${validation.summary.clubCounts[0].club}`
                    : "\u2014"}
                </dd>
              </div>
            </dl>
            <p>
              {saved ? (
                <>
                  Locked in. Your{" "}
                  <Link to={`/plan?team=${String(entryId)}`}>
                    gameweek 1 to 38 plan
                  </Link>{" "}
                  now starts from these fifteen.
                </>
              ) : (
                "This squad is legal. Lock it in to plan the season from it."
              )}
            </p>
            <p className="record-caveat">
              The eleven figure is last season&rsquo;s scoring record, before
              fixtures and before the captain. It is what is measurable today,
              not a projection of this season.
            </p>
          </>
        ) : (
          <>
            <p>I will not hold a squad that could not be entered:</p>
            <ul className="declared-squad-problems">
              {validation.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
