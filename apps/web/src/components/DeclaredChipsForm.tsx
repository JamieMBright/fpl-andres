import { useEffect, useState } from "react";

import {
  CHIPS,
  CHIP_NAMES,
  chipsFromHistory,
  chipsRemaining,
  halfForEvent,
  readDeclaredChips,
  saveDeclaredChips,
  type Chip,
  type DeclaredChips,
} from "../state/declared-chips";
import { entryHistorySchema } from "../state/manager-profile";

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
  // Which rows came off FPL's own record rather than a manual toggle, so the
  // manager is only ever asked to correct what FPL has not processed yet.
  const [inferredKeys, setInferredKeys] = useState<ReadonlySet<string>>(
    new Set(),
  );

  function commit(next: DeclaredChips) {
    const saved = saveDeclaredChips(window.localStorage, entryId, next);
    setChips(saved);
    onDeclared(saved);
  }

  useEffect(() => {
    const controller = new AbortController();
    async function read() {
      try {
        const response = await fetch(
          `/api/fpl/entry/${String(entryId)}/history`,
          {
            signal: controller.signal,
          },
        );
        if (!response.ok) return;
        const parsed = entryHistorySchema.safeParse(
          await response.json().catch(() => null),
        );
        if (!parsed.success) return;
        const inferred = chipsFromHistory(parsed.data.chips);
        if (inferred.length === 0) return;
        setInferredKeys(
          new Set(inferred.map((entry) => `${entry.chip}:${entry.half}`)),
        );
        setChips((current) => {
          const merged = [
            ...new Map(
              [...current.spent, ...inferred].map((entry) => [
                `${entry.chip}:${entry.half}`,
                entry,
              ]),
            ).values(),
          ];
          if (merged.length === current.spent.length) return current;
          const saved = saveDeclaredChips(window.localStorage, entryId, {
            ...current,
            spent: merged,
          });
          onDeclared(saved);
          return saved;
        });
      } catch {
        // FPL unreachable: the manual toggles below are the fallback.
      }
    }
    void read();
    return () => {
      controller.abort();
    };
    // onDeclared is a fresh closure every render in the caller; keying the
    // fetch to it would re-read FPL on every unrelated re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entryId]);

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
        Chips FPL has already processed are ticked from your own record below.
        Toggle one by hand only for a chip played too recently for FPL to have
        processed yet, and set one you have committed to. The plan will not
        recommend a chip twice or schedule around a decision you have made.
      </p>

      <fieldset className="declared-chips-spent">
        <legend>Chips already played</legend>
        {(["first", "second"] as const).map((half) => (
          <div key={half}>
            <strong>{half === "first" ? "First half" : "Second half"}</strong>
            {CHIPS.map((chip) => {
              const rowKey = `${chip}:${half}`;
              const checked = chips.spent.some(
                (entry) => entry.chip === chip && entry.half === half,
              );
              const inferred = inferredKeys.has(rowKey);
              return (
                <label className="chip-toggle" key={rowKey}>
                  <input
                    checked={checked}
                    disabled={inferred}
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
                  <span>
                    {CHIP_NAMES[chip]}
                    {inferred ? (
                      <small className="chip-toggle-source">
                        {" "}
                        · from your record
                      </small>
                    ) : null}
                  </span>
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
