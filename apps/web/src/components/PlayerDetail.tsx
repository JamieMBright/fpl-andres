import { useEffect, useRef } from "react";

import { CeefaxShirt } from "./CeefaxShirt";
import type { FixtureRun } from "../state/fixture-run";
import { kitForShortName } from "../kit/team-kits";
import type { Band } from "../state/stat-bands";
import { bandFor } from "../state/stat-bands";
import { projectionFor, projectionSeason } from "../state/squad-projection";
import type { PlayerProjection } from "../state/squad-projection";
import { money as sharedMoney } from "../format";

/** The least a caller must know to open this card. */
export interface DetailPlayer {
  code: number;
  name: string;
  position: string;
  club: string;
  priceTenths: number;
  /** FPL's availability flag. Undefined where the caller does not read it. */
  available?: boolean;
  squadNumber?: number | null;
}

function money(valueTenths: number): string {
  return `${sharedMoney.format(valueTenths / 10)}m`;
}

function percent(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : `${Math.round(value * 100)}%`;
}

interface Row {
  term: string;
  value: string;
  /** Why the number is here at all. Nothing on this card is decoration. */
  explains: string;
  /** How it stands against others in the position. Null where it cannot be. */
  band: Band | null;
}

function rowsFor(player: DetailPlayer, record: PlayerProjection | null): Row[] {
  if (!record) return [];
  const perMillion =
    player.priceTenths > 0
      ? record.expectedPoints / (player.priceTenths / 10)
      : null;
  const band = (field: Parameters<typeof bandFor>[1], value: number | null) =>
    bandFor(player.position, field, value);

  return [
    {
      term: "Points per match",
      value: record.expectedPoints.toFixed(2),
      explains: `Expected FPL points in one match against an average opponent, rebuilt from his ${projectionSeason} per-90 rates and minutes.`,
      band: band("expectedPoints", record.expectedPoints),
    },
    {
      term: "Per £1m",
      value: perMillion?.toFixed(2) ?? "—",
      explains: "Points per match divided by what he costs today.",
      band: null,
    },
    {
      term: "Minutes",
      value: Math.round(record.expectedMinutes).toString(),
      explains: "Expected minutes in one match, from last season's pattern.",
      band: band("expectedMinutes", record.expectedMinutes),
    },
    {
      term: "Starts",
      value: percent(record.probabilityStart),
      explains: "How often he was in the starting eleven when available.",
      band: band("probabilityStart", record.probabilityStart),
    },
    {
      term: "Appears",
      value: percent(record.probabilityAppear),
      explains: "How often he got on the pitch at all.",
      band: band("probabilityAppear", record.probabilityAppear),
    },
    {
      term: "Appearances",
      value: record.appearances.toString(),
      explains: `Matches played in ${projectionSeason}.`,
      band: band("appearances", record.appearances),
    },
    {
      term: "Returned",
      value: percent(record.returnRate),
      explains: "Share of appearances with a goal or an assist.",
      band: band("returnRate", record.returnRate),
    },
    {
      term: "Blanked",
      value: percent(record.blankRate),
      explains: "Share of appearances scoring two points or fewer.",
      band: band("blankRate", record.blankRate),
    },
    {
      term: "Floor",
      value: record.floor?.toString() ?? "—",
      explains: "His tenth-percentile match last season.",
      band: band("floor", record.floor),
    },
    {
      term: "Median",
      value: record.median?.toString() ?? "—",
      explains: "His middling match last season.",
      band: band("median", record.median),
    },
    {
      term: "Ceiling",
      value: record.ceiling?.toString() ?? "—",
      explains: "His best single match last season.",
      band: band("ceiling", record.ceiling),
    },
    {
      term: "Yellow cards",
      value: record.yellowCards.toString(),
      explains:
        "Five yellows in the first nineteen matches is a one-match ban; ten by matchweek thirty-two is two; fifteen across the season is three.",
      band: band("yellowCards", record.yellowCards),
    },
    {
      term: "Suspension derate",
      value: `×${record.suspensionMultiplier.toFixed(2)}`,
      explains:
        "What his booking rate costs him over the next five matches, applied to his points.",
      band: band("suspensionMultiplier", record.suspensionMultiplier),
    },
  ];
}

const ROUTE_LABELS: [keyof PlayerProjection["routes"], string][] = [
  ["appearance", "Turning up"],
  ["attacking", "Goals and assists"],
  ["cleanSheet", "Clean sheets"],
  ["bonus", "Bonus"],
  ["saves", "Saves"],
  ["conceding", "Goals conceded"],
  ["discipline", "Cards and misses"],
  ["defensiveContribution", "Defensive actions"],
];

/**
 * One player, in full, without leaving the table.
 *
 * The table shows what fits in a row. This shows the rest, and says what each
 * number means, because a figure you cannot interpret is not evidence.
 */
export function PlayerDetail({
  onClose,
  player,
  run = null,
}: {
  onClose: () => void;
  player: DetailPlayer;
  /** Omitted where the caller has no fixture ratings to hand. */
  run?: FixtureRun | null;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  // `showModal` rather than the `open` attribute: it is what gives the platform
  // dialog its focus trap, its Escape handling and its inert backdrop. Writing
  // those by hand is how a modal ends up unusable with a keyboard.
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
  }, []);

  const record = projectionFor(player.code);
  const rows = rowsFor(player, record);
  const kit = kitForShortName(player.club);
  const defensive = player.position === "GKP" || player.position === "DEF";

  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events -- The rule does not know `dialog` is interactive. Opened with `showModal`, it is dismissible from the keyboard with Escape and by the Close button below; this handler only adds click-outside for a mouse.
    <dialog
      aria-labelledby="player-detail-name"
      className="player-detail"
      // The backdrop is part of the dialog's own box, so a click that lands
      // outside the card is a click on the dialog itself.
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
      onClose={onClose}
      ref={dialog}
    >
      <div className="player-detail-card">
        <button className="player-detail-close" onClick={onClose} type="button">
          Close
        </button>

        <header className="player-detail-head">
          {kit ? (
            <span className="player-detail-kit">
              <CeefaxShirt
                className="player-detail-shirt"
                kit={kit}
                label={null}
                squadNumber={player.squadNumber ?? null}
              />
              {player.squadNumber === null ||
              player.squadNumber === undefined ? (
                // Said out loud rather than hidden in a tooltip. FPL ships a
                // `squad_number` field and leaves it null for all 570 players,
                // so a blank shirt is the source being empty, not a bug here.
                <small className="player-detail-nonumber">
                  FPL publishes no squad number
                </small>
              ) : null}
            </span>
          ) : (
            <span aria-hidden="true" className="player-detail-shirt" />
          )}
          <div>
            <h2 id="player-detail-name" translate="no">
              {player.name}
            </h2>
            <p className="mono">
              {player.position} · <span translate="no">{player.club}</span> ·{" "}
              {money(player.priceTenths)}
              {player.available === false ? " · flagged by FPL" : null}
            </p>
          </div>
        </header>

        {rows.length === 0 ? (
          <p className="player-detail-empty">
            He has no Premier League record in the seasons I hold, so there is
            nothing here to show you. That is a gap in the evidence, not a
            verdict on the player.
          </p>
        ) : (
          <dl className="player-detail-stats">
            {rows.map(({ term, value, explains, band }) => (
              <div key={term}>
                <dt title={explains}>{term}</dt>
                <dd className={band ? `mono band-${band}` : "mono"}>{value}</dd>
                <p>{explains}</p>
              </div>
            ))}
          </dl>
        )}

        {rows.length > 0 ? (
          <p className="player-detail-key">
            Figures are coloured against everyone else in his position:{" "}
            <span className="band-poor">below most</span>,{" "}
            <span className="band-ordinary">ordinary</span>,{" "}
            <span className="band-useful">above most</span>,{" "}
            <span className="band-strong">among the best</span>. Four points a
            match is excellent for a defender and unremarkable for a forward,
            which is why the comparison is within the position rather than
            across the game.
          </p>
        ) : null}

        {record ? (
          <section className="player-detail-routes">
            <h3>Where the points come from</h3>
            <ul className="mono">
              {ROUTE_LABELS.filter(
                ([key]) => Math.abs(record.routes[key]) >= 0.005,
              ).map(([key, label]) => (
                <li key={key}>
                  <span>{label}</span>
                  <span>{record.routes[key].toFixed(2)}</span>
                </li>
              ))}
            </ul>
            <p>
              These add up to the points-per-match figure above, before the
              suspension derate. A fixture moves each of them differently, which
              is why a hard away tie is bad for a defender&rsquo;s clean sheet
              and good for his keeper&rsquo;s saves.
            </p>
          </section>
        ) : null}

        <section className="player-detail-run">
          <h3>Next five</h3>
          {run === null || run.rating === null ? (
            <p>
              I have no rating for these fixtures, so nothing is shown rather
              than a guess.
            </p>
          ) : (
            <>
              <ol className="mono">
                {run.opponents.map((opponent, index) => (
                  <li key={`${opponent}-${index.toString()}`}>
                    {opponent || "—"}
                  </li>
                ))}
              </ol>
              <p>
                Rated {run.rating.toFixed(2)} on what these opponents{" "}
                {defensive ? "score" : "concede"} against an average side. One
                is average
                {run.rated < run.fixtures
                  ? `; only ${run.rated.toString()} of ${run.fixtures.toString()} could be rated`
                  : ""}
                .
              </p>
            </>
          )}
        </section>
      </div>
    </dialog>
  );
}
