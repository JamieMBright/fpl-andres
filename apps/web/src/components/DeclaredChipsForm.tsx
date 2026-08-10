import { useState } from "react";

import {
  CHIPS,
  CHIP_NAMES,
  readDeclaredChips,
  saveDeclaredChips,
  type Chip,
  type DeclaredChips,
} from "../state/declared-chips";

/**
 * What the manager has already decided, which FPL does not publish.
 *
 * The plan schedules four chips across a season and has no way of knowing that
 * two of them are gone. It will keep offering a wildcard played in August for
 * the rest of the year, which is not a small error: the wildcard is the single
 * biggest move in the game and every transfer around it is planned against it.
 *
 * A committed chip is the other half. A manager who has decided on a Triple
 * Captain for a double gameweek has changed the shape of the weeks either side
 * of it, and a plan that argues with a decision already made is a plan he stops
 * reading.
 */
export function DeclaredChipsForm({
  entryId,
  onDeclared,
}: {
  entryId: number;
  onDeclared: (chips: DeclaredChips) => void;
}) {
  const [chips, setChips] = useState<DeclaredChips>(() =>
    readDeclaredChips(window.localStorage, entryId),
  );

  function commit(next: DeclaredChips) {
    const saved = saveDeclaredChips(window.localStorage, entryId, next);
    setChips(saved);
    onDeclared(saved);
  }

  return (
    <form
      aria-labelledby="declared-chips"
      className="declared-chips"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <h2 id="declared-chips">Anything you have already decided</h2>
      <p>
        FPL publishes the chip you played last gameweek and nothing else, so the
        plan cannot see a wildcard you spent in August or a Triple Captain you
        have committed to. Tell it here and it plans around both.
      </p>

      <fieldset className="declared-chips-spent">
        <legend>Chips already played</legend>
        {CHIPS.map((chip) => (
          <label key={chip}>
            <input
              checked={chips.spent.includes(chip)}
              onChange={(event) => {
                commit({
                  ...chips,
                  spent: event.target.checked
                    ? [...chips.spent, chip]
                    : chips.spent.filter((held) => held !== chip),
                });
              }}
              type="checkbox"
            />
            {CHIP_NAMES[chip]}
          </label>
        ))}
      </fieldset>

      <div className="declared-chips-commit">
        <label htmlFor="chip-committed">Committing to</label>
        <select
          id="chip-committed"
          onChange={(event) => {
            const chip = event.target.value as Chip | "";
            commit({
              ...chips,
              committed:
                chip === ""
                  ? null
                  : { chip, event: chips.committed?.event ?? 1 },
            });
          }}
          value={chips.committed?.chip ?? ""}
        >
          <option value="">nothing yet</option>
          {CHIPS.filter((chip) => !chips.spent.includes(chip)).map((chip) => (
            <option key={chip} value={chip}>
              {CHIP_NAMES[chip]}
            </option>
          ))}
        </select>
        <label htmlFor="chip-event">in gameweek</label>
        <input
          disabled={chips.committed === null}
          id="chip-event"
          max={38}
          min={1}
          onChange={(event) => {
            const week = Number(event.target.value);
            if (!chips.committed || !Number.isInteger(week)) return;
            if (week < 1 || week > 38) return;
            commit({
              ...chips,
              committed: { ...chips.committed, event: week },
            });
          }}
          type="number"
          value={chips.committed?.event ?? ""}
        />
      </div>

      <p className="field-hint">
        Kept in this browser and sent nowhere. A Team ID is public, so anything
        a server handed back could have been typed by somebody else.
      </p>
    </form>
  );
}
