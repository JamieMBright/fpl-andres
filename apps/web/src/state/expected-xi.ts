import playerOddsData from "../data/player-odds.json";
import seasonInputsData from "../data/season-inputs.json";
import manualPriorsData from "../data/xstart-manual-priors.json";
import { TEAM_KITS } from "../kit/team-kits";
import {
  XSTART_VALIDATION,
  type XStartClubValidation,
  type XStartValidation,
} from "./xstart-validation";

type PositionCode = "GKP" | "DEF" | "MID" | "FWD";

type ExpectedXiEvidence = "manual" | "market" | "model" | "prior";

interface SeasonInputPlayer {
  id: number;
  code: number;
  name: string;
  position: PositionCode;
  club: string;
  teamId: number;
  startRate: number;
  availabilityStatus?: string;
  chanceOfPlaying?: number | null;
  rated?: boolean;
  startEvidence?: {
    sourceStartRate?: number;
    finalStartRate?: number;
    observedAppearances?: number | null;
    recentStarts?: number | null;
    recentMatches?: number | null;
    recentMinutes?: number | null;
    appearanceSource?: string;
    marketAdjustment?: number;
  };
}

interface SeasonInputsArtifact {
  generatedAt: string;
  events?: readonly number[];
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

interface ManualPriorRow {
  elementId: number;
  code: number;
  club: string;
  name: string;
  startProbability: number;
  confidence: string;
  reason: string;
}

interface ManualPriorArtifact {
  generatedAt: string;
  source: string;
  players: readonly ManualPriorRow[];
}

export interface ExpectedXiFactor {
  label: string;
  value: string;
  detail: string;
}

export interface ExpectedXiExplanation {
  title: string;
  factors: ExpectedXiFactor[];
  updatedAt: string | null;
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
  availabilityStatus: string | null;
  chanceOfPlaying: number | null;
  explanation: ExpectedXiExplanation;
}

export interface ExpectedXiTeam {
  club: string;
  name: string;
  starters: ExpectedXiPlayer[];
  reserves: ExpectedXiPlayer[];
  availabilityFlags: ExpectedXiPlayer[];
  averageStartProbability: number;
  marketStatus: string;
  playersQuoted: number;
  quoteFloor: number;
  unmatchedNames: readonly string[];
  teamSheetEvidence: "dated" | "unavailable";
  updatedAt: string | null;
  validation?: XStartClubValidation;
}

export interface ExpectedXi {
  event: number;
  generatedAt: string;
  marketUpdatedAt: string | null;
  teams: ExpectedXiTeam[];
  validation?: XStartValidation;
}

interface ExpectedXiInputs {
  seasonInputs: SeasonInputsArtifact;
  playerOdds: PlayerOddsArtifact;
  manualPriors?: ManualPriorArtifact;
}

const clubNames = new Map(TEAM_KITS.map((team) => [team.shortName, team.name]));
const clubOrder = new Map(
  TEAM_KITS.map((team, index) => [team.shortName, index]),
);

function toPlayer(
  player: SeasonInputPlayer,
  quotedIds: ReadonlySet<number>,
  carriedIds: ReadonlySet<string>,
  inputs: ExpectedXiInputs,
  manual: ManualPriorRow | undefined,
  blocker: ManualPriorRow | undefined,
): ExpectedXiPlayer {
  const quoted = quotedIds.has(player.id);
  const carried = carriedIds.has(String(player.id));
  const startProbability = manual
    ? manual.startProbability
    : blocker && player.position === "GKP"
      ? Math.min(player.startRate, 0.01)
      : player.startRate;
  const evidence: ExpectedXiEvidence = manual
    ? "manual"
    : quoted || carried
      ? "market"
      : player.rated === false
        ? "prior"
        : "model";
  const factors: ExpectedXiFactor[] = [
    {
      label: "Model",
      value: `${Math.round(player.startRate * 100)}%`,
      detail:
        player.rated === false
          ? "Role prior, not a measured record."
          : "Season-input start rate.",
    },
  ];
  const startEvidence = player.startEvidence;
  if (startEvidence) {
    const sourceRate =
      typeof startEvidence.sourceStartRate === "number"
        ? `${Math.round(startEvidence.sourceStartRate * 100)}%`
        : "unpublished";
    const finalRate =
      typeof startEvidence.finalStartRate === "number"
        ? `${Math.round(startEvidence.finalStartRate * 100)}%`
        : `${Math.round(startProbability * 100)}%`;
    const observed =
      typeof startEvidence.observedAppearances === "number"
        ? `${startEvidence.observedAppearances} recorded appearances`
        : "recorded appearances unavailable";
    const recent =
      typeof startEvidence.recentStarts === "number" &&
      typeof startEvidence.recentMatches === "number"
        ? `${startEvidence.recentStarts}/${startEvidence.recentMatches} recent starts`
        : "recent starts unavailable";
    factors[0] = {
      label: "Math",
      value: finalRate,
      detail: `${sourceRate} source rate -> ${finalRate} published rate; ${observed}; ${recent}. The artifact does not publish the prior strength or effective sample size yet.`,
    };
    if (typeof startEvidence.marketAdjustment === "number") {
      factors.push({
        label: "Market effect",
        value: `${startEvidence.marketAdjustment >= 0 ? "+" : ""}${Math.round(startEvidence.marketAdjustment * 100)}pp`,
        detail:
          startEvidence.appearanceSource === "marketParticipation"
            ? "Bookmaker player participation changed the model input by this amount."
            : startEvidence.appearanceSource === "marketAbsence"
              ? "Absence from a complete player market pulled the model input by this amount."
              : "No bookmaker participation adjustment was applied.",
      });
    }
  }
  if (quoted || carried) {
    factors.push({
      label: "Market",
      value: quoted ? "Quoted" : "Carry",
      detail: quoted
        ? "Named in the current player market scrape."
        : "A quoted fixture view is fading back toward history.",
    });
  }
  if (manual) {
    factors.push({
      label: "Manual",
      value: `${Math.round(manual.startProbability * 100)}%`,
      detail: manual.reason,
    });
  } else if (blocker && player.position === "GKP") {
    factors.push({
      label: "Manual",
      value: "Blocked",
      detail: `${blocker.name} is set as the high-confidence starting goalkeeper.`,
    });
  }
  if (player.availabilityStatus && player.availabilityStatus !== "a") {
    const names: Record<string, string> = {
      d: "Doubtful",
      i: "Injured",
      s: "Suspended",
      u: "Unavailable",
      n: "Not in squad",
    };
    factors.push({
      label: "FPL availability",
      value: names[player.availabilityStatus] ?? player.availabilityStatus,
      detail:
        player.chanceOfPlaying === null || player.chanceOfPlaying === undefined
          ? "FPL has flagged him without publishing a percentage."
          : `FPL publishes a ${player.chanceOfPlaying}% chance of playing.`,
    });
  }
  return {
    id: player.id,
    code: player.code,
    name: player.name,
    position: player.position,
    club: player.club,
    startProbability,
    evidence,
    quoted,
    availabilityStatus: player.availabilityStatus ?? null,
    chanceOfPlaying: player.chanceOfPlaying ?? null,
    explanation: {
      title: `${player.name} xStart ${Math.round(startProbability * 100)}%`,
      factors,
      updatedAt: manual
        ? (inputs.manualPriors?.generatedAt ?? null)
        : inputs.seasonInputs.generatedAt,
    },
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
  const manualById = new Map(
    (inputs.manualPriors?.players ?? []).map((prior) => [
      prior.elementId,
      prior,
    ]),
  );
  const manualStartingKeeper = (inputs.manualPriors?.players ?? []).find(
    (prior) =>
      prior.club === club &&
      prior.startProbability >= 0.99 &&
      players.some(
        (player) => player.id === prior.elementId && player.position === "GKP",
      ),
  );
  const adjustedSort = (
    left: SeasonInputPlayer,
    right: SeasonInputPlayer,
  ): number => {
    const leftPrior = manualById.get(left.id);
    const rightPrior = manualById.get(right.id);
    const leftRate = leftPrior
      ? leftPrior.startProbability
      : manualStartingKeeper && left.position === "GKP"
        ? Math.min(left.startRate, 0.01)
        : left.startRate;
    const rightRate = rightPrior
      ? rightPrior.startProbability
      : manualStartingKeeper && right.position === "GKP"
        ? Math.min(right.startRate, 0.01)
        : right.startRate;
    return rightRate - leftRate || left.name.localeCompare(right.name);
  };
  const keepers = players
    .filter((player) => player.position === "GKP")
    .sort(adjustedSort);
  const outfield = players
    .filter((player) => player.position !== "GKP")
    .sort(adjustedSort);
  const starterRows = [...keepers.slice(0, 1), ...outfield.slice(0, 10)];
  const starterIds = new Set(starterRows.map((player) => player.id));
  const convert = (player: SeasonInputPlayer) =>
    toPlayer(
      player,
      quotedIds,
      carriedIds,
      inputs,
      manualById.get(player.id),
      manualStartingKeeper?.elementId === player.id
        ? undefined
        : manualStartingKeeper,
    );
  const reserves = players
    .filter((player) => !starterIds.has(player.id))
    .sort(adjustedSort)
    .slice(0, 7)
    .map(convert);
  const starters = starterRows.map(convert);
  const displayedIds = new Set(
    [...starters, ...reserves].map((player) => player.id),
  );
  const availabilityFlags = players
    .filter(
      (player) =>
        player.availabilityStatus &&
        player.availabilityStatus !== "a" &&
        !displayedIds.has(player.id),
    )
    .sort(adjustedSort)
    .map(convert);
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
    availabilityFlags,
    averageStartProbability,
    marketStatus:
      diagnostic?.status ?? (quotedIds.size > 0 ? "returned" : "unvisited"),
    playersQuoted: quotedIds.size,
    quoteFloor: inputs.playerOdds.clubQuoteFloor ?? 18,
    unmatchedNames: diagnostic?.unmatched_names ?? [],
    teamSheetEvidence: manualPriorsForClub(inputs.manualPriors, club)
      ? "dated"
      : "unavailable",
    updatedAt:
      diagnostic?.visited_at ??
      (quotedIds.size > 0 ? inputs.playerOdds.fetchedAt : null),
  };
}

function manualPriorsForClub(
  artifact: ManualPriorArtifact | undefined,
  club: string,
): ManualPriorRow | undefined {
  return artifact?.players.find((prior) => prior.club === club);
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
    event: inputs.seasonInputs.events?.[0] ?? 2,
    generatedAt: inputs.seasonInputs.generatedAt,
    marketUpdatedAt:
      inputs.seasonInputs.evidence?.playerMarkets?.updatedAt ??
      inputs.playerOdds.fetchedAt,
    teams,
  };
}

export function expectedXi(): ExpectedXi {
  const built = buildExpectedXi({
    seasonInputs: seasonInputsData as SeasonInputsArtifact,
    playerOdds: playerOddsData as PlayerOddsArtifact,
    manualPriors: manualPriorsData as ManualPriorArtifact,
  });
  const validationByClub = new Map(
    XSTART_VALIDATION.clubs.map((club) => [club.club, club]),
  );
  return {
    ...built,
    validation: XSTART_VALIDATION,
    teams: built.teams.map((team) => {
      const validation = validationByClub.get(team.club);
      return validation ? { ...team, validation } : team;
    }),
  };
}
