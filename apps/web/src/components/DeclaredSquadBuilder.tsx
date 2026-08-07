import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { CeefaxShirt } from "./CeefaxShirt";
import { money } from "../format";
import { kitForShortName } from "../kit/team-kits";
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

type SquadPlayer = NonNullable<
  ReturnType<(typeof PLAYERS_BY_ELEMENT_ID)["get"]>
>;

/** One place on the pitch: a shirt and a price, or an empty outline. */
function SquadSlot({
  player,
  position,
  onClear,
}: {
  player: SquadPlayer | null;
  position: string;
  onClear: () => void;
}) {
  if (!player) {
    return (
      <div className="squad-slot squad-slot-empty">
        <span className="squad-slot-position mono">{position}</span>
      </div>
    );
  }

  // A club with no kit drawn yet gets the name and the price but no shirt,
  // rather than another club's colours.
  const kit = kitForShortName(player.club);

  return (
    <div className="squad-slot">
      <button
        aria-label={`Remove ${player.name}`}
        className="squad-slot-clear"
        onClick={onClear}
        type="button"
      >
        ×
      </button>
      <span className="squad-slot-price mono">
        {pounds(player.priceTenths)}
      </span>
      {kit ? <CeefaxShirt kit={kit} label={null} /> : null}
      <span className="squad-slot-name">{player.name}</span>
      <span className="squad-slot-club mono">{player.club}</span>
    </div>
  );
}

/** The list you pick from, filtered the way the official transfer page filters. */
function SquadMarket({
  players,
  picked,
  remainingTenths,
  onAdd,
}: {
  players: readonly SquadPlayer[];
  picked: ReadonlySet<number>;
  remainingTenths: number;
  onAdd: (player: SquadPlayer) => void;
}) {
  const [position, setPosition] = useState("ALL");
  const [maxTenths, setMaxTenths] = useState(155);
  const [search, setSearch] = useState("");

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return players
      .filter((player) => position === "ALL" || player.position === position)
      .filter((player) => player.priceTenths <= maxTenths)
      .filter(
        (player) =>
          !needle ||
          player.name.toLowerCase().includes(needle) ||
          player.club.toLowerCase().includes(needle),
      )
      .sort((left, right) => right.priceTenths - left.priceTenths);
  }, [players, position, maxTenths, search]);

  return (
    <div className="squad-market">
      <div className="squad-market-filters">
        <select
          aria-label="Position"
          onChange={(changed) => {
            setPosition(changed.target.value);
          }}
          value={position}
        >
          <option value="ALL">All players</option>
          {SLOTS.map((slot) => (
            <option key={slot.position} value={slot.position}>
              {slot.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Maximum price"
          onChange={(changed) => {
            setMaxTenths(Number(changed.target.value));
          }}
          value={maxTenths}
        >
          {[155, 130, 110, 90, 75, 60, 50, 45].map((tenths) => (
            <option key={tenths} value={tenths}>
              {pounds(tenths)}
            </option>
          ))}
        </select>
        <input
          aria-label="Search by name or club"
          onChange={(changed) => {
            setSearch(changed.target.value);
          }}
          placeholder="Search"
          type="search"
          value={search}
        />
      </div>

      <p className="squad-market-count mono">
        {shown.length} shown · {pounds(remainingTenths)} left
      </p>

      <ol className="squad-market-list">
        {shown.slice(0, 120).map((player) => {
          const already = picked.has(player.id);
          const tooDear = player.priceTenths > remainingTenths;
          return (
            <li key={player.id}>
              <span className="squad-market-name">{player.name}</span>
              <span className="squad-market-club mono">
                {player.club} {player.position}
              </span>
              <span className="squad-market-price mono">
                {pounds(player.priceTenths)}
              </span>
              <button
                aria-label={`Add ${player.name}`}
                disabled={already || tooDear}
                onClick={() => {
                  onAdd(player);
                }}
                title={
                  already
                    ? "Already in your fifteen"
                    : tooDear
                      ? "More than you have left"
                      : "Add"
                }
                type="button"
              >
                +
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
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

  /** Drop a player into the first free slot of his own position. */
  const addPlayer = (player: SquadPlayer) => {
    const group = SLOTS.find((slot) => slot.position === player.position);
    if (!group) return;
    const free = Array.from(
      { length: group.count },
      (_u, o) => group.offset + o,
    ).find((index) => !picks[index]);
    if (free === undefined) return;
    setSlot(free, String(player.id));
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
        FPL keeps every squad private until the first deadline, so there is
        nothing public to read yet. Name your fifteen and I will plan the season
        from it. It stays in this browser.
      </p>

      <div className="squad-builder">
        <SquadMarket
          onAdd={addPlayer}
          picked={new Set(chosen)}
          players={players}
          remainingTenths={SQUAD_BUDGET_TENTHS - spentTenths}
        />

        <div className="squad-pitch">
          {SLOTS.map((group) => (
            <div className="squad-pitch-row" key={group.position}>
              {Array.from({ length: group.count }, (_unused, offset) => {
                const index = group.offset + offset;
                const elementId = Number(picks[index] ?? "");
                const player = PLAYERS_BY_ELEMENT_ID.get(elementId) ?? null;
                return (
                  <SquadSlot
                    key={index}
                    onClear={() => {
                      setSlot(index, "");
                    }}
                    player={player}
                    position={group.position}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="declared-squad-actions">
        <button
          className="primary-command"
          disabled={validation?.valid !== true}
          onClick={lockIn}
          type="button"
        >
          Lock this in for gameweek 1
        </button>
        <button className="secondary-command" onClick={clear} type="button">
          Clear
        </button>
      </div>

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
