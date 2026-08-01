import projections from "../data/projections.json";
import {
  PROJECTIONS_SCHEMA_VERSION,
  requireArtifactVersion,
} from "./artifact-version";

requireArtifactVersion(
  "projections.json",
  projections,
  PROJECTIONS_SCHEMA_VERSION,
);

/** Attack and defence multipliers against the league average, by venue. */
export interface ClubStrength {
  code: number;
  shortName: string;
  attackHome: number;
  attackAway: number;
  defenceHome: number;
  defenceAway: number;
}

const clubs = new Map(
  ((projections as { clubs?: ClubStrength[] }).clubs ?? []).map((club) => [
    club.code,
    club,
  ]),
);

export interface ScheduledFixture {
  event: number | null;
  team_h: number;
  team_a: number;
}

export interface FixtureRun {
  /**
   * Mean opponent multiplier over the run, on the route that matters for this
   * position: what the opponents score for a goalkeeper or defender, what they
   * concede for a midfielder or forward. One is average.
   *
   * Null when nothing in the run can be rated.
   */
  rating: number | null;
  /** How many of the fixtures had a rateable opponent. */
  rated: number;
  /** How many fixtures the club has in the window, blanks and doubles included. */
  fixtures: number;
  /** Opponent short names in order, an empty string where the club is new. */
  opponents: string[];
}

/**
 * Rate a club's next few fixtures using last season's measured strength.
 *
 * A single difficulty number is wrong for this game, so the rating is route
 * specific: a hard fixture is bad for a clean sheet and good for saves. A club
 * that was not in the division last season has no measurement and is left
 * unrated rather than assumed average — three of the twenty are promoted every
 * year and treating them as typical is exactly the error that costs you a
 * gameweek.
 */
export function rateFixtureRun(
  clubCodeByTeamId: ReadonlyMap<number, number>,
  fixtures: readonly ScheduledFixture[],
  teamId: number,
  position: string,
  window: number,
): FixtureRun {
  const defensive = position === "GKP" || position === "DEF";
  const events = [
    ...new Set(
      fixtures
        .map((fixture) => fixture.event)
        .filter((event): event is number => event !== null),
    ),
  ]
    .sort((left, right) => left - right)
    .slice(0, window);
  const horizon = new Set(events);

  const run = fixtures.filter(
    (fixture) =>
      fixture.event !== null &&
      horizon.has(fixture.event) &&
      (fixture.team_h === teamId || fixture.team_a === teamId),
  );

  const multipliers: number[] = [];
  const opponents: string[] = [];

  for (const fixture of run) {
    const home = fixture.team_h === teamId;
    const opponentId = home ? fixture.team_a : fixture.team_h;
    const code = clubCodeByTeamId.get(opponentId);
    const opponent = code === undefined ? undefined : clubs.get(code);
    opponents.push(opponent?.shortName ?? "");
    if (!opponent) continue;

    // The opponent plays the opposite venue to this club.
    multipliers.push(
      defensive
        ? home
          ? opponent.attackAway
          : opponent.attackHome
        : home
          ? opponent.defenceAway
          : opponent.defenceHome,
    );
  }

  return {
    rating:
      multipliers.length === 0
        ? null
        : round(
            multipliers.reduce((total, value) => total + value, 0) /
              multipliers.length,
          ),
    rated: multipliers.length,
    fixtures: run.length,
    opponents,
  };
}

export function clubStrength(code: number | undefined): ClubStrength | null {
  return code === undefined ? null : (clubs.get(code) ?? null);
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
