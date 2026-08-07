import type { RunMatch } from "../state/fixture-run";

/**
 * A spell is a stretch of consecutive rated fixtures that runs clearly with or
 * clearly against the player. Three is the shortest run worth naming: two ties
 * is noise, and a stretch you cannot plan a transfer around is not a spell.
 */
const SPELL_LENGTH = 3;

/**
 * How far a spell's mean has to sit from average before it is called one.
 * The multipliers are ratios around one, so 0.12 is a twelve per cent swing in
 * what the opposition does — big enough to move a captaincy, small enough that
 * a real season contains a few.
 */
const SPELL_MARGIN = 0.12;

export interface Spell {
  from: number;
  to: number;
  mean: number;
  kind: "good" | "hard";
}

/**
 * Find the stretches worth naming.
 *
 * Every window of `SPELL_LENGTH` consecutive rated fixtures is scored, the ones
 * far enough from average are kept, and overlapping windows of the same kind
 * are merged so a six-week run reads as one spell rather than four.
 *
 * `favourHigh` is what makes this position specific: for a forward a high
 * multiplier means the opponents concede freely and the spell is good, while
 * for a defender the same number means they score freely and it is hard.
 */
export function findSpells(
  matches: readonly RunMatch[],
  favourHigh: boolean,
): Spell[] {
  const rated = matches.filter(
    (match): match is RunMatch & { multiplier: number } =>
      match.multiplier !== null,
  );
  const found: Spell[] = [];

  for (let start = 0; start + SPELL_LENGTH <= rated.length; start += 1) {
    const window = rated.slice(start, start + SPELL_LENGTH);

    // Only contiguous gameweeks: a window that straddles a blank, or a week
    // against a club I hold no measurement for, is not a run of fixtures I can
    // vouch for. Bridging it would claim the schedule is soft across a week I
    // cannot rate at all.
    const contiguous = window.every((match, index) => {
      const previous = window[index - 1];
      return previous === undefined || match.event <= previous.event + 1;
    });
    if (!contiguous) continue;

    const mean =
      window.reduce((total, match) => total + match.multiplier, 0) /
      window.length;
    const swing = favourHigh ? mean - 1 : 1 - mean;
    if (Math.abs(swing) < SPELL_MARGIN) continue;

    const kind = swing > 0 ? "good" : "hard";
    const first = window[0];
    const last = window[window.length - 1];
    if (first === undefined || last === undefined) continue;
    const from = first.event;
    const to = last.event;
    const previous = found[found.length - 1];

    if (previous && previous.kind === kind && from <= previous.to + 1) {
      previous.to = to;
      continue;
    }
    found.push({ from, to, mean, kind });
  }

  // The merged spells were widened after their means were taken, so each one is
  // rescored over the stretch it actually covers.
  return found.map((spell) => {
    const covered = rated.filter(
      (match) => match.event >= spell.from && match.event <= spell.to,
    );
    return {
      ...spell,
      mean:
        covered.reduce((total, match) => total + match.multiplier, 0) /
        covered.length,
    };
  });
}

/** Where a single tie sits, as a class rather than an inline colour. */
function toneOf(multiplier: number | null, favourHigh: boolean): string {
  if (multiplier === null) return "unrated";
  const swing = favourHigh ? multiplier - 1 : 1 - multiplier;
  if (swing >= SPELL_MARGIN) return "good";
  if (swing <= -SPELL_MARGIN) return "hard";
  return "even";
}

/**
 * The remaining season as one strip, so a reader can see where the schedule
 * turns rather than only what happens next.
 *
 * Five fixtures answers "should I transfer him in this week". It cannot answer
 * "is he worth holding through the winter", which is the question a season plan
 * is actually made of.
 */
export function SeasonFixtures({
  matches,
  defensive,
}: {
  matches: readonly RunMatch[];
  /** True for goalkeepers and defenders, whose route is the opponent's attack. */
  defensive: boolean;
}) {
  const favourHigh = !defensive;
  const spells = findSpells(matches, favourHigh);

  if (matches.length === 0) {
    return (
      <p>
        The calendar holds no further fixtures for this club, so there is
        nothing to show.
      </p>
    );
  }

  return (
    <div className="season-fixtures">
      <ol className="season-fixtures-strip">
        {matches.map((match) => (
          <li
            className={`season-fixture tone-${toneOf(match.multiplier, favourHigh)}`}
            key={`${match.event.toString()}-${match.opponent}-${match.home ? "H" : "A"}`}
          >
            <span className="season-fixture-event mono">
              {match.event.toString()}
            </span>
            <span className="season-fixture-opponent mono">
              {match.opponent || "—"}
              {match.opponent ? (match.home ? " (H)" : " (A)") : ""}
            </span>
          </li>
        ))}
      </ol>

      {spells.length === 0 ? (
        <p>
          Nothing in the run is far enough from average to call a good or a hard
          spell. That is a finding, not a gap: this club&rsquo;s schedule is
          level.
        </p>
      ) : (
        <ul className="season-spells">
          {spells.map((spell) => (
            <li
              className={`season-spell tone-${spell.kind}`}
              key={`${spell.kind}-${spell.from.toString()}`}
            >
              <strong>
                {spell.kind === "good" ? "Good spell" : "Hard spell"}
              </strong>{" "}
              <span className="mono">
                GW{spell.from.toString()}
                {spell.to === spell.from ? "" : `–${spell.to.toString()}`}
              </span>{" "}
              — opponents {defensive ? "score" : "concede"}{" "}
              <span className="mono">{spell.mean.toFixed(2)}</span> times what
              an average side does.
            </li>
          ))}
        </ul>
      )}

      <p>
        One is average. A tie is shaded only once it is{" "}
        {(SPELL_MARGIN * 100).toFixed(0)}% either side of it, and a spell needs{" "}
        {SPELL_LENGTH.toString()} consecutive gameweeks holding that swing.
        Unshaded ties are opponents I hold no measured Premier League season
        for, so they are left blank rather than assumed average.
      </p>
    </div>
  );
}
