import playerOddsData from "../data/player-odds.json";
import seasonInputsData from "../data/season-inputs.json";
import { TEAM_KITS } from "../kit/team-kits";

type PositionCode = "GKP" | "DEF" | "MID" | "FWD";

type ExpectedXiEvidence = "market" | "model" | "prior";

interface SeasonInputPlayer {
  id: number;
  code: number;
  name: string;
  position: PositionCode;
  club: string;
  teamId: number;
  startRate: number;
  rated?: boolean;
}

interface SeasonInputsArtifact {
  generatedAt: string;
  players: readonly SeasonInputPlayer[];
  marketCarry?: { players?: Record<string, readonly unknown[]> };
  evidence?: {
    playerMarkets?: {
      level?: string;
      updatedAt?: string | null;
    };
  };
}

interface PlayerOddsRow {
  element_id: number | null;
  club: string | null;
  kickoff: string | null;
}

interface FixtureDiagnostic {
  home_short: string | null;
  away_short: string | null;
  visited_at: string | null;
  status: string;
  unmatched_names: readonly string[];
}

interface PlayerOddsArtifact {
  fetchedAt: string;
  clubQuoteFloor?: number;
  fixtures?: readonly FixtureDiagnostic[];
  players: readonly PlayerOddsRow[];
}

export interface ExpectedXiPlayer {
  id: number;
  code: number;
  name: string;
  position: PositionCode;
  club: string;
  startProbability: number;
  evidence: ExpectedXiEvidence;
  quoted: boolean;
}

export interface ExpectedXiTeam {
  club: string;
  name: string;
  starters: ExpectedXiPlayer[];
  reserves: ExpectedXiPlayer[];
  averageStartProbability: number;
  marketStatus: string;
  playersQuoted: number;
  quoteFloor: number;
  unmatchedNames: readonly string[];
  updatedAt: string | null;
}

export interface ExpectedXi {
  generatedAt: string;
  marketUpdatedAt: string | null;
  teams: ExpectedXiTeam[];
}

interface ExpectedXiInputs {
  seasonInputs: SeasonInputsArtifact;
  playerOdds: PlayerOddsArtifact;
}

const clubNames = new Map(TEAM_KITS.map((team) => [team.shortName, team.name]));
const clubOrder = new Map(
  TEAM_KITS.map((team, index) => [team.shortName, index]),
);

function probabilitySort(
  left: SeasonInputPlayer,
  right: SeasonInputPlayer,
): number {
  return (
    right.startRate - left.startRate || left.name.localeCompare(right.name)
  );
}

function toPlayer(
  player: SeasonInputPlayer,
  quotedIds: ReadonlySet<number>,
  carriedIds: ReadonlySet<string>,
): ExpectedXiPlayer {
  const quoted = quotedIds.has(player.id);
  const evidence: ExpectedXiEvidence =
    quoted || carriedIds.has(String(player.id))
      ? "market"
      : player.rated === false
        ? "prior"
        : "model";
  return {
    id: player.id,
    code: player.code,
    name: player.name,
    position: player.position,
    club: player.club,
    startProbability: player.startRate,
    evidence,
    quoted,
  };
}

function diagnosticFor(
  playerOdds: PlayerOddsArtifact,
  club: string,
): FixtureDiagnostic | null {
  return (
    playerOdds.fixtures?.find(
      (fixture) => fixture.home_short === club || fixture.away_short === club,
    ) ?? null
  );
}

function buildTeam(
  club: string,
  players: readonly SeasonInputPlayer[],
  inputs: ExpectedXiInputs,
): ExpectedXiTeam {
  const quotedIds = new Set(
    inputs.playerOdds.players.flatMap((row) =>
      row.club === club && typeof row.element_id === "number"
        ? [row.element_id]
        : [],
    ),
  );
  const carriedIds = new Set(
    Object.keys(inputs.seasonInputs.marketCarry?.players ?? {}),
  );
  const keepers = players
    .filter((player) => player.position === "GKP")
    .sort(probabilitySort);
  const outfield = players
    .filter((player) => player.position !== "GKP")
    .sort(probabilitySort);
  const starterRows = [...keepers.slice(0, 1), ...outfield.slice(0, 10)];
  const starterIds = new Set(starterRows.map((player) => player.id));
  const reserves = players
    .filter((player) => !starterIds.has(player.id))
    .sort(probabilitySort)
    .slice(0, 7)
    .map((player) => toPlayer(player, quotedIds, carriedIds));
  const starters = starterRows.map((player) =>
    toPlayer(player, quotedIds, carriedIds),
  );
  const diagnostic = diagnosticFor(inputs.playerOdds, club);
  const averageStartProbability =
    starters.length === 0
      ? 0
      : starters.reduce((total, player) => total + player.startProbability, 0) /
        starters.length;
  return {
    club,
    name: clubNames.get(club) ?? club,
    starters,
    reserves,
    averageStartProbability,
    marketStatus:
      diagnostic?.status ?? (quotedIds.size > 0 ? "returned" : "unvisited"),
    playersQuoted: quotedIds.size,
    quoteFloor: inputs.playerOdds.clubQuoteFloor ?? 18,
    unmatchedNames: diagnostic?.unmatched_names ?? [],
    updatedAt:
      diagnostic?.visited_at ??
      (quotedIds.size > 0 ? inputs.playerOdds.fetchedAt : null),
  };
}

export function buildExpectedXi(inputs: ExpectedXiInputs): ExpectedXi {
  const byClub = new Map<string, SeasonInputPlayer[]>();
  for (const player of inputs.seasonInputs.players) {
    byClub.set(player.club, [...(byClub.get(player.club) ?? []), player]);
  }
  const teams = [...byClub]
    .map(([club, players]) => buildTeam(club, players, inputs))
    .sort(
      (left, right) =>
        (clubOrder.get(left.club) ?? Number.MAX_SAFE_INTEGER) -
          (clubOrder.get(right.club) ?? Number.MAX_SAFE_INTEGER) ||
        left.club.localeCompare(right.club),
    );
  return {
    generatedAt: inputs.seasonInputs.generatedAt,
    marketUpdatedAt:
      inputs.seasonInputs.evidence?.playerMarkets?.updatedAt ??
      inputs.playerOdds.fetchedAt,
    teams,
  };
}

export function expectedXi(): ExpectedXi {
  return buildExpectedXi({
    seasonInputs: seasonInputsData as SeasonInputsArtifact,
    playerOdds: playerOddsData as PlayerOddsArtifact,
  });
}
