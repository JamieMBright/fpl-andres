import type { VercelRequest, VercelResponse } from "@vercel/node";

import fixtureOddsData from "../../apps/web/src/data/fixture-odds.json" with { type: "json" };
import deadlinesData from "../../apps/web/src/data/deadlines.json" with { type: "json" };
import playerOddsData from "../../apps/web/src/data/player-odds.json" with { type: "json" };
import seasonInputsData from "../../apps/web/src/data/season-inputs.json" with { type: "json" };
import seasonPlanData from "../../apps/web/src/data/season-plan.json" with { type: "json" };
import manualPriorsData from "../../apps/web/src/data/xstart-manual-priors.json" with { type: "json" };
import xstartValidationData from "../../apps/web/src/data/xstart-validation.json" with { type: "json" };
import {
  requireArtifactVersion,
  SEASON_PLAN_SCHEMA_VERSION,
  XSTART_VALIDATION_SCHEMA_VERSION,
} from "../../apps/web/src/state/artifact-version.js";

import {
  clientAddress,
  rateLimitHeaders,
  RateLimiter,
  RECOMMENDATIONS_POLICY,
} from "./rate-limit.js";

type Endpoint = "latest" | "markets" | "meta" | "xstart";

interface PlanPlayer {
  code: number;
  name: string;
  position: string;
  club: string;
  priceTenths: number;
}

interface PlanArtifact {
  schemaVersion: number;
  modelVersion: string;
  generatedAt: string;
  season: string;
  recordSeason: string;
  basis: string;
  netExpectedPoints: number;
  chips: unknown[];
  players: Record<string, Omit<PlanPlayer, "code">>;
  gameweeks: {
    event: number;
    deadline: string;
    confidence: string;
    starters: number[];
    bench: number[];
    captain: number;
    viceCaptain: number;
    transfersIn: number[];
    transfersOut: number[];
    expected: Record<string, number>;
    netExpectedPoints: number;
  }[];
}

interface SeasonInputsArtifact {
  schemaVersion: number;
  generatedAt: string;
  recordSeason: string;
  evidence?: { playerMarkets?: { updatedAt?: string | null } };
  marketCarry?: { players?: Record<string, unknown> };
  players: {
    id: number;
    code: number;
    name: string;
    position: string;
    club: string;
    startRate: number;
    rated?: boolean;
  }[];
}

interface PlayerOddsArtifact {
  schemaVersion: number;
  fetchedAt: string;
  season: string;
  markets: string[];
  quota?: unknown;
  coverage?: unknown;
  fixtures?: { kickoff?: string | null }[];
  players: {
    element_id: number | null;
    club: string | null;
    kickoff?: string | null;
  }[];
}

interface ManualPriorsArtifact {
  generatedAt: string;
  source: string;
  players: {
    elementId: number;
    name: string;
    club: string;
    startProbability: number;
    reason: string;
  }[];
}

interface FixtureOddsArtifact {
  schemaVersion: number;
  generatedAt: string;
  season: string;
  source: string;
  fixtures: { kickoff?: string | null }[];
}

interface DeadlineArtifact {
  deadlines: { event: number; deadline: string; finished: boolean }[];
}

interface XStartValidationArtifact {
  schemaVersion: number;
  event: number;
  modelVersion: string;
  field: string;
  population: {
    count: number;
    brier: number;
    logLoss: number;
    meanForecast: number;
    actualStartRate: number;
  };
  topEleven: { hits: number; actualStarters: number; recall: number | null };
  clubs: unknown[];
}

const limiter = new RateLimiter(RECOMMENDATIONS_POLICY);
const PLAN = seasonPlanData as unknown as PlanArtifact;
const INPUTS = seasonInputsData as unknown as SeasonInputsArtifact;
const PLAYER_ODDS = playerOddsData as unknown as PlayerOddsArtifact;
const FIXTURE_ODDS = fixtureOddsData as unknown as FixtureOddsArtifact;
const DEADLINES = deadlinesData as unknown as DeadlineArtifact;
const MANUAL_PRIORS = manualPriorsData as unknown as ManualPriorsArtifact;
const XSTART_VALIDATION =
  xstartValidationData as unknown as XStartValidationArtifact;

requireArtifactVersion("season-plan", PLAN, SEASON_PLAN_SCHEMA_VERSION);
requireArtifactVersion(
  "xstart-validation",
  XSTART_VALIDATION,
  XSTART_VALIDATION_SCHEMA_VERSION,
);
if (
  XSTART_VALIDATION.field !== "probabilitySixtyMinutesAsShipped" ||
  !Array.isArray(XSTART_VALIDATION.clubs) ||
  XSTART_VALIDATION.clubs.length !== 20
) {
  throw new Error("xstart-validation is missing its shipped field and clubs");
}

function planPlayer(plan: PlanArtifact, code: number): PlanPlayer {
  const found = plan.players[String(code)];
  if (!found)
    return {
      code,
      name: String(code),
      position: "UNK",
      club: "UNK",
      priceTenths: 0,
    };
  return { code, ...found };
}

function meta() {
  return {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    modelVersion: PLAN.modelVersion,
    artifacts: {
      seasonPlan: {
        schemaVersion: PLAN.schemaVersion,
        generatedAt: PLAN.generatedAt,
      },
      seasonInputs: {
        schemaVersion: INPUTS.schemaVersion,
        generatedAt: INPUTS.generatedAt,
      },
      playerOdds: {
        schemaVersion: PLAYER_ODDS.schemaVersion,
        fetchedAt: PLAYER_ODDS.fetchedAt,
      },
      fixtureOdds: {
        schemaVersion: FIXTURE_ODDS.schemaVersion,
        generatedAt: FIXTURE_ODDS.generatedAt,
      },
    },
  };
}

function latest() {
  const week = PLAN.gameweeks[0];
  if (!week)
    return { schemaVersion: 1, status: "unavailable", reason: "no_gameweeks" };
  return {
    schemaVersion: 1,
    status: "ready",
    generatedAt: PLAN.generatedAt,
    season: PLAN.season,
    recordSeason: PLAN.recordSeason,
    modelVersion: PLAN.modelVersion,
    deadline: week.deadline,
    event: week.event,
    confidence: week.confidence,
    captain: planPlayer(PLAN, week.captain),
    viceCaptain: planPlayer(PLAN, week.viceCaptain),
    transfersIn: week.transfersIn.map((code) => planPlayer(PLAN, code)),
    transfersOut: week.transfersOut.map((code) => planPlayer(PLAN, code)),
    bench: week.bench.map((code) => planPlayer(PLAN, code)),
    netExpectedPoints: week.netExpectedPoints,
    chips: PLAN.chips,
    evidence: {
      level: week.confidence,
      sources: ["season-plan", "season-inputs", "fixture-odds", "player-odds"],
    },
  };
}

function currentMarketWindow() {
  const upcoming = [...DEADLINES.deadlines]
    .filter((row) => !row.finished)
    .sort(
      (left, right) => Date.parse(left.deadline) - Date.parse(right.deadline),
    );
  const current = upcoming[0];
  const following = upcoming.find(
    (row) => current !== undefined && row.event > current.event,
  );
  const includes = (kickoff: string | null | undefined) => {
    if (current === undefined || typeof kickoff !== "string") return false;
    const instant = Date.parse(kickoff);
    return (
      instant > Date.parse(current.deadline) &&
      (following === undefined || instant < Date.parse(following.deadline))
    );
  };
  return { current, includes };
}

function xstart() {
  const marketWindow = currentMarketWindow();
  const quoted = new Set(
    PLAYER_ODDS.players.flatMap((row) =>
      typeof row.element_id === "number" && marketWindow.includes(row.kickoff)
        ? [row.element_id]
        : [],
    ),
  );
  const carried = new Set(Object.keys(INPUTS.marketCarry?.players ?? {}));
  const manualById = new Map(
    MANUAL_PRIORS.players.map((row) => [row.elementId, row]),
  );
  const byClub = new Map<string, typeof INPUTS.players>();
  for (const player of INPUTS.players) {
    byClub.set(player.club, [...(byClub.get(player.club) ?? []), player]);
  }
  return {
    schemaVersion: 1,
    generatedAt: INPUTS.generatedAt,
    marketUpdatedAt:
      INPUTS.evidence?.playerMarkets?.updatedAt ?? PLAYER_ODDS.fetchedAt,
    manualUpdatedAt: MANUAL_PRIORS.generatedAt,
    modelVersion: PLAN.modelVersion,
    shippedFieldValidation: XSTART_VALIDATION,
    teams: [...byClub].sort().map(([club, players]) => {
      const manualKeeper = MANUAL_PRIORS.players.find(
        (row) => row.club === club && row.startProbability >= 0.99,
      );
      const ranked = [...players].sort((left, right) => {
        const leftManual = manualById.get(left.id);
        const rightManual = manualById.get(right.id);
        const leftRate = leftManual
          ? leftManual.startProbability
          : manualKeeper && left.position === "GKP"
            ? Math.min(left.startRate, 0.01)
            : left.startRate;
        const rightRate = rightManual
          ? rightManual.startProbability
          : manualKeeper && right.position === "GKP"
            ? Math.min(right.startRate, 0.01)
            : right.startRate;
        return rightRate - leftRate || left.name.localeCompare(right.name);
      });
      return {
        club,
        players: ranked.map((player) => {
          const manualRow = manualById.get(player.id);
          const blocked =
            manualKeeper &&
            manualKeeper.elementId !== player.id &&
            player.position === "GKP";
          return {
            elementId: player.id,
            code: player.code,
            name: player.name,
            position: player.position,
            startProbability: manualRow
              ? manualRow.startProbability
              : blocked
                ? Math.min(player.startRate, 0.01)
                : player.startRate,
            evidence: manualRow
              ? "manual"
              : quoted.has(player.id) || carried.has(String(player.id))
                ? "market"
                : player.rated === false
                  ? "prior"
                  : "model",
            reason:
              manualRow?.reason ??
              (blocked
                ? `${manualKeeper.name} is set as the high-confidence starting goalkeeper.`
                : "Season-input start rate."),
          };
        }),
      };
    }),
  };
}

function markets() {
  const marketWindow = currentMarketWindow();
  const fixtures = FIXTURE_ODDS.fixtures.filter((fixture) =>
    marketWindow.includes(fixture.kickoff),
  );
  const playerFixtures = (PLAYER_ODDS.fixtures ?? []).filter((fixture) =>
    marketWindow.includes(fixture.kickoff),
  );
  const players = PLAYER_ODDS.players.filter((player) =>
    marketWindow.includes(player.kickoff),
  );
  return {
    schemaVersion: 1,
    status: fixtures.length > 0 ? "ready" : "stale",
    reason: fixtures.length > 0 ? null : "post-fixture",
    event: marketWindow.current?.event ?? null,
    generatedAt: new Date().toISOString(),
    modelVersion: PLAN.modelVersion,
    fixtureOdds: {
      generatedAt: FIXTURE_ODDS.generatedAt,
      season: FIXTURE_ODDS.season,
      source: FIXTURE_ODDS.source,
      fixtures,
    },
    playerOdds: {
      fetchedAt: PLAYER_ODDS.fetchedAt,
      season: PLAYER_ODDS.season,
      markets: PLAYER_ODDS.markets,
      quota: PLAYER_ODDS.quota,
      coverage: PLAYER_ODDS.coverage,
      fixtures: playerFixtures,
      players,
    },
  };
}

function body(endpoint: Endpoint): unknown {
  if (endpoint === "latest") return latest();
  if (endpoint === "xstart") return xstart();
  if (endpoint === "markets") return markets();
  return meta();
}

export function recommendationsHandler(endpoint: Endpoint) {
  return (request: VercelRequest, response: VercelResponse): void => {
    if (request.method !== "GET" && request.method !== "HEAD") {
      response.setHeader("Allow", "GET, HEAD");
      response.status(405).json({ error: "Use GET.", reason: "method" });
      return;
    }
    const decision = limiter.check(clientAddress(request.headers));
    for (const [name, value] of Object.entries(
      rateLimitHeaders(RECOMMENDATIONS_POLICY, decision),
    )) {
      response.setHeader(name, value);
    }
    response.setHeader(
      "Cache-Control",
      "public, max-age=60, stale-while-revalidate=300",
    );
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    if (!decision.allowed) {
      response
        .status(429)
        .json({ error: "Too many requests.", reason: "rate_limited" });
      return;
    }
    response.status(200).json(body(endpoint));
  };
}
