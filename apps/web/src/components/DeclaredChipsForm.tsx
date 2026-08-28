import { useState } from "react";

import {
  CHIPS,
  CHIP_NAMES,
  chipsRemaining,
  halfForEvent,
  readDeclaredChips,
  saveDeclaredChips,
  type Chip,
  type DeclaredChips,
} from "../state/declared-chips";

/**
 * What the manager has already decided, which FPL does not publish.
 *
 * The plan schedules two half-season copies of each chip and has no way of
 * knowing which are gone. It will keep offering a wildcard played in August
 * for the first half, which is not a small error: the wildcard is the single
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
      <h3 id="declared-chips">Chip decisions FPL cannot see</h3>
      <p>
        Mark chips already used and one you have committed to. The plan will not
        recommend a chip twice or schedule around a decision you have made.
      </p>

      <fieldset className="declared-chips-spent">
        <legend>Chips already played</legend>
        {(["first", "second"] as const).map((half) => (
          <div key={half}>
            <strong>{half === "first" ? "First half" : "Second half"}</strong>
            {CHIPS.map((chip) => {
              const checked = chips.spent.some(
                (entry) => entry.chip === chip && entry.half === half,
              );
              return (
                <label key={`${half}-${chip}`}>
                  <input
                    checked={checked}
                    onChange={(event) => {
                      commit({
                        ...chips,
                        spent: event.target.checked
                          ? [...chips.spent, { chip, half }]
                          : chips.spent.filter(
                              (entry) =>
                                entry.chip !== chip || entry.half !== half,
                            ),
                      });
                    }}
                    type="checkbox"
                  />
                  {CHIP_NAMES[chip]}
                </label>
              );
            })}
          </div>
        ))}
      </fieldset>

      <div className="declared-chips-commit">
        <label htmlFor="chip-committed">Committing to</label>
        <select
          id="chip-committed"
          onChange={(event) => {
            const chip = event.target.value as Chip | "";
            const defaultEvent =
              chip !== "" && chipsRemaining(chips, "first").includes(chip)
                ? 1
                : 20;
            commit({
              ...chips,
              committed:
                chip === ""
                  ? null
                  : { chip, event: chips.committed?.event ?? defaultEvent },
            });
          }}
          value={chips.committed?.chip ?? ""}
        >
          <option value="">nothing yet</option>
          {CHIPS.filter(
            (chip) =>
              chipsRemaining(chips, "first").includes(chip) ||
              chipsRemaining(chips, "second").includes(chip),
          ).map((chip) => (
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
              committed: chips.spent.some(
                (entry) =>
                  entry.chip === chips.committed?.chip &&
                  entry.half === halfForEvent(week),
              )
                ? null
                : { ...chips.committed, event: week },
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
