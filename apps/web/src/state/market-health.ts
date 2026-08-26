import deadlinesData from "../data/deadlines.json";
import fixtureOddsData from "../data/fixture-odds.json";
import playerOddsData from "../data/player-odds.json";
import seasonInputsData from "../data/season-inputs.json";

export const MARKET_EXPECTATION_HOURS = 72;

const TEAM_MARKETS = [
  ["h2h", "Match result"],
  ["h2h_lay", "Exchange lay"],
  ["totals", "Goals over/under"],
  ["alternate_totals", "Alternate goal lines"],
] as const;

const PLAYER_MARKETS = [
  ["player_goal_scorer_anytime", "Anytime scorer", "anytime_goal"],
  ["player_first_goal_scorer", "First scorer", "first_goal"],
  ["player_last_goal_scorer", "Last scorer", "last_goal"],
  ["player_assists", "Anytime assist", "anytime_assist"],
  ["player_to_receive_card", "Any card", "any_card"],
  ["player_to_receive_red_card", "Red card", "red_card"],
  ["player_shots", "Total shots", "shots"],
  ["player_shots_on_target", "Shots on target", "shots_on_target"],
] as const;

type MarketVerdict = "ready" | "partial" | "deadline-anomaly" | "unavailable";
type MarketKind = "team" | "player";

interface FixtureOddsRow {
  kickoff: string;
  home: string;
  away: string;
  homeExpectedGoals: number;
  awayExpectedGoals: number;
  homeCleanSheet: number;
  awayCleanSheet: number;
  marketEvidence?: { observed: string[] };
}

interface FixtureOddsArtifact {
  generatedAt: string;
  fixtures: FixtureOddsRow[];
}

function observedTeamMarkets(fixture: FixtureOddsRow): ReadonlySet<string> {
  return new Set(fixture.marketEvidence?.observed ?? []);
}

interface PlayerOddsRow {
  element_id: number | null;
  quoted_name?: string;
  club: string | null;
  kickoff: string | null;
  books?: number;
  observed_at?: string;
  [key: string]: unknown;
}

interface SeasonInputPlayer {
  id: number;
  name: string;
  position: string;
  priceTenths: number;
  startRate: number;
  depthRank?: number;
}

interface SeasonInputsArtifact {
  players: readonly SeasonInputPlayer[];
}

interface FixtureDiagnostic {
  home_short: string | null;
  away_short: string | null;
  kickoff: string | null;
  status: string;
  visited_at: string | null;
  unmatched_names: string[];
}

interface PlayerOddsArtifact {
  fetchedAt: string;
  markets: string[];
  clubQuoteFloor?: number;
  fixtures?: FixtureDiagnostic[];
  players: PlayerOddsRow[];
}

interface DeadlineArtifact {
  deadlines: { event: number; deadline: string; finished: boolean }[];
}

export interface MarketClassHealth {
  key: string;
  label: string;
  kind: MarketKind;
  fixturesCovered: number;
  fixturesExpected: number;
  status: "complete" | "partial" | "missing";
}

export interface TeamMarketHealth {
  club: string;
  opponent: string;
  venue: "H" | "A";
  kickoff: string;
  expectedGoals: number;
  cleanSheetProbability: number;
  teamMarketsCovered: number;
  teamMarketsExpected: number;
  playerMarketsCovered: number;
  playerMarketsExpected: number;
  playersQuoted: number;
  quoteFloor: number;
  providerStatus: string;
  visitedAt: string | null;
  unmatchedNames: readonly string[];
  players: readonly PlayerMarketHealth[];
}

export interface PlayerMarketHealth {
  elementId: number | null;
  quotedName: string;
  name: string;
  position: string | null;
  priceTenths: number | null;
  startRate: number | null;
  depthRank: number | null;
  books: number | null;
  observedAt: string | null;
  markets: Record<string, number | null>;
}

export interface MarketHealth {
  verdict: MarketVerdict;
  event: number | null;
  deadline: string | null;
  hoursUntilDeadline: number | null;
  fixtureMarketsAsOf: string;
  playerMarketsAsOf: string;
  playerArtifactAgeHours: number | null;
  fixturesExpected: number;
  teamFixturesCovered: number;
  playerFixturesCovered: number;
  markets: MarketClassHealth[];
  teams: TeamMarketHealth[];
}

interface MarketHealthInputs {
  fixtureOdds: FixtureOddsArtifact;
  playerOdds: PlayerOddsArtifact;
  deadlines: DeadlineArtifact;
  seasonInputs?: SeasonInputsArtifact;
}

function hoursBetween(later: Date, earlier: Date): number | null {
  const milliseconds = later.getTime() - earlier.getTime();
  return Number.isFinite(milliseconds) ? milliseconds / 3_600_000 : null;
}

function sameInstant(left: string | null, right: string): boolean {
  return left !== null && Date.parse(left) === Date.parse(right);
}

function coverageStatus(covered: number, expected: number) {
  if (covered === 0) return "missing" as const;
  return covered >= expected ? ("complete" as const) : ("partial" as const);
}

function fixtureDiagnostic(
  artifact: PlayerOddsArtifact,
  fixture: FixtureOddsRow,
): FixtureDiagnostic | null {
  return (
    artifact.fixtures?.find(
      (row) =>
        row.home_short === fixture.home &&
        row.away_short === fixture.away &&
        sameInstant(row.kickoff, fixture.kickoff),
    ) ?? null
  );
}

function fixtureRows(
  artifact: PlayerOddsArtifact,
  fixture: FixtureOddsRow,
): PlayerOddsRow[] {
  return artifact.players.filter((row) =>
    sameInstant(row.kickoff, fixture.kickoff),
  );
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function playerMarketHealth(
  row: PlayerOddsRow,
  playerById: ReadonlyMap<number, SeasonInputPlayer>,
): PlayerMarketHealth {
  const player =
    typeof row.element_id === "number"
      ? playerById.get(row.element_id)
      : undefined;
  return {
    elementId: row.element_id,
    quotedName: row.quoted_name ?? player?.name ?? "Unmatched player",
    name: player?.name ?? row.quoted_name ?? "Unmatched player",
    position: player?.position ?? null,
    priceTenths: player?.priceTenths ?? null,
    startRate: player?.startRate ?? null,
    depthRank: player?.depthRank ?? null,
    books: nullableNumber(row.books),
    observedAt: typeof row.observed_at === "string" ? row.observed_at : null,
    markets: Object.fromEntries(
      PLAYER_MARKETS.map(([, label, field]) => [
        label,
        nullableNumber(row[field]),
      ]),
    ),
  };
}

function teamHealth(
  fixture: FixtureOddsRow,
  club: string,
  venue: "H" | "A",
  artifact: PlayerOddsArtifact,
  seasonInputs: SeasonInputsArtifact,
): TeamMarketHealth {
  const rows = fixtureRows(artifact, fixture).filter(
    (row) => row.club === club,
  );
  const playerById = new Map(
    seasonInputs.players.map((player) => [player.id, player]),
  );
  const diagnostic = fixtureDiagnostic(artifact, fixture);
  const observed = observedTeamMarkets(fixture);
  const playerMarketsCovered = PLAYER_MARKETS.filter(([, , field]) =>
    rows.some((row) => typeof row[field] === "number"),
  ).length;
  const playersQuoted = new Set(
    rows.flatMap((row) =>
      typeof row.element_id === "number" ? [row.element_id] : [],
    ),
  ).size;
  return {
    club,
    opponent: venue === "H" ? fixture.away : fixture.home,
    venue,
    kickoff: fixture.kickoff,
    expectedGoals:
      venue === "H" ? fixture.homeExpectedGoals : fixture.awayExpectedGoals,
    cleanSheetProbability:
      venue === "H" ? fixture.homeCleanSheet : fixture.awayCleanSheet,
    teamMarketsCovered: TEAM_MARKETS.filter(([key]) => observed.has(key))
      .length,
    teamMarketsExpected: TEAM_MARKETS.length,
    playerMarketsCovered,
    playerMarketsExpected: PLAYER_MARKETS.length,
    playersQuoted,
    quoteFloor: artifact.clubQuoteFloor ?? 18,
    providerStatus:
      diagnostic?.status ??
      (fixtureRows(artifact, fixture).length > 0 ? "returned" : "unvisited"),
    visitedAt:
      diagnostic?.visited_at ??
      (fixtureRows(artifact, fixture).length > 0 ? artifact.fetchedAt : null),
    unmatchedNames: diagnostic?.unmatched_names ?? [],
    players: rows
      .map((row) => playerMarketHealth(row, playerById))
      .sort(
        (left, right) =>
          (right.startRate ?? -1) - (left.startRate ?? -1) ||
          left.name.localeCompare(right.name),
      ),
  };
}

export function buildMarketHealth(
  inputs: MarketHealthInputs,
  now: Date = new Date(),
): MarketHealth {
  const { fixtureOdds, playerOdds, deadlines } = inputs;
  const seasonInputs =
    inputs.seasonInputs ?? (seasonInputsData as SeasonInputsArtifact);
  const next = [...deadlines.deadlines]
    .filter((row) => !row.finished)
    .sort(
      (left, right) => Date.parse(left.deadline) - Date.parse(right.deadline),
    )[0];
  const following = [...deadlines.deadlines]
    .filter(
      (row) =>
        next !== undefined &&
        row.event > next.event &&
        Date.parse(row.deadline) > Date.parse(next.deadline),
    )
    .sort(
      (left, right) => Date.parse(left.deadline) - Date.parse(right.deadline),
    )[0];
  const deadline = next?.deadline ?? null;
  const fixtures = fixtureOdds.fixtures.filter((fixture) => {
    if (deadline === null) return false;
    const kickoff = Date.parse(fixture.kickoff);
    return (
      kickoff > Date.parse(deadline) &&
      (following === undefined || kickoff < Date.parse(following.deadline))
    );
  });
  const hoursUntilDeadline = deadline
    ? hoursBetween(new Date(deadline), now)
    : null;
  const playerArtifactAgeHours = hoursBetween(
    now,
    new Date(playerOdds.fetchedAt),
  );
  const fixturesExpected = fixtures.length;
  const teamFixturesCovered = fixtures.filter((fixture) =>
    TEAM_MARKETS.every(([key]) => observedTeamMarkets(fixture).has(key)),
  ).length;
  const playerFixturesCovered = fixtures.filter(
    (fixture) => fixtureRows(playerOdds, fixture).length > 0,
  ).length;

  const markets: MarketClassHealth[] = [
    ...TEAM_MARKETS.map(([key, label]) => {
      const fixturesCovered = fixtures.filter((fixture) =>
        observedTeamMarkets(fixture).has(key),
      ).length;
      return {
        key,
        label,
        kind: "team" as const,
        fixturesCovered,
        fixturesExpected,
        status: coverageStatus(fixturesCovered, fixturesExpected),
      };
    }),
    ...PLAYER_MARKETS.map(([key, label, field]) => {
      const fixturesCovered = fixtures.filter((fixture) =>
        fixtureRows(playerOdds, fixture).some(
          (row) => typeof row[field] === "number",
        ),
      ).length;
      return {
        key,
        label,
        kind: "player" as const,
        fixturesCovered,
        fixturesExpected,
        status: coverageStatus(fixturesCovered, fixturesExpected),
      };
    }),
  ];
  const playerClassesComplete = markets
    .filter((market) => market.kind === "player")
    .every((market) => market.status === "complete");
  let verdict: MarketVerdict = "partial";
  if (deadline === null || fixturesExpected === 0) {
    verdict = "unavailable";
  } else if (
    hoursUntilDeadline !== null &&
    hoursUntilDeadline <= MARKET_EXPECTATION_HOURS &&
    (!playerClassesComplete || playerFixturesCovered < fixturesExpected)
  ) {
    verdict = "deadline-anomaly";
  } else if (
    playerClassesComplete &&
    playerFixturesCovered === fixturesExpected &&
    teamFixturesCovered === fixturesExpected
  ) {
    verdict = "ready";
  }

  return {
    verdict,
    event: next?.event ?? null,
    deadline,
    hoursUntilDeadline,
    fixtureMarketsAsOf: fixtureOdds.generatedAt,
    playerMarketsAsOf: playerOdds.fetchedAt,
    playerArtifactAgeHours,
    fixturesExpected,
    teamFixturesCovered,
    playerFixturesCovered,
    markets,
    teams: fixtures.flatMap((fixture) => [
      teamHealth(fixture, fixture.home, "H", playerOdds, seasonInputs),
      teamHealth(fixture, fixture.away, "A", playerOdds, seasonInputs),
    ]),
  };
}

export function marketHealth(now: Date = new Date()): MarketHealth {
  return buildMarketHealth(
    {
      fixtureOdds: fixtureOddsData as FixtureOddsArtifact,
      playerOdds: playerOddsData as PlayerOddsArtifact,
      deadlines: deadlinesData as DeadlineArtifact,
      seasonInputs: seasonInputsData as SeasonInputsArtifact,
    },
    now,
  );
}
