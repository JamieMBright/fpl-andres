import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { VercelRequest, VercelResponse } from "@vercel/node";

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
  fixtures?: unknown[];
  players: { element_id: number | null; club: string | null }[];
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
  fixtures: unknown[];
}

interface ManifestArtifact {
  modelVersion?: string;
}

const ROOT = process.cwd();
const limiter = new RateLimiter(RECOMMENDATIONS_POLICY);

function jsonFile<T>(path: string): T {
  return JSON.parse(readFileSync(join(ROOT, path), "utf8")) as T;
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

function modelVersion(): string | null {
  try {
    return (
      jsonFile<ManifestArtifact>("data/prospective/gw1-2026-27.json")
        .modelVersion ?? null
    );
  } catch {
    return null;
  }
}

function meta() {
  const plan = jsonFile<PlanArtifact>("apps/web/src/data/season-plan.json");
  const inputs = jsonFile<SeasonInputsArtifact>(
    "apps/web/src/data/season-inputs.json",
  );
  const playerOdds = jsonFile<PlayerOddsArtifact>(
    "apps/web/src/data/player-odds.json",
  );
  const fixtureOdds = jsonFile<FixtureOddsArtifact>(
    "apps/web/src/data/fixture-odds.json",
  );
  return {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    modelVersion: modelVersion(),
    artifacts: {
      seasonPlan: {
        schemaVersion: plan.schemaVersion,
        generatedAt: plan.generatedAt,
      },
      seasonInputs: {
        schemaVersion: inputs.schemaVersion,
        generatedAt: inputs.generatedAt,
      },
      playerOdds: {
        schemaVersion: playerOdds.schemaVersion,
        fetchedAt: playerOdds.fetchedAt,
      },
      fixtureOdds: {
        schemaVersion: fixtureOdds.schemaVersion,
        generatedAt: fixtureOdds.generatedAt,
      },
    },
  };
}

function latest() {
  const plan = jsonFile<PlanArtifact>("apps/web/src/data/season-plan.json");
  const week = plan.gameweeks[0];
  if (!week)
    return { schemaVersion: 1, status: "unavailable", reason: "no_gameweeks" };
  return {
    schemaVersion: 1,
    status: "ready",
    generatedAt: plan.generatedAt,
    season: plan.season,
    recordSeason: plan.recordSeason,
    modelVersion: modelVersion(),
    deadline: week.deadline,
    event: week.event,
    confidence: week.confidence,
    captain: planPlayer(plan, week.captain),
    viceCaptain: planPlayer(plan, week.viceCaptain),
    transfersIn: week.transfersIn.map((code) => planPlayer(plan, code)),
    transfersOut: week.transfersOut.map((code) => planPlayer(plan, code)),
    bench: week.bench.map((code) => planPlayer(plan, code)),
    netExpectedPoints: week.netExpectedPoints,
    chips: plan.chips,
    evidence: {
      level: week.confidence,
      sources: ["season-plan", "season-inputs", "fixture-odds", "player-odds"],
    },
  };
}

function xstart() {
  const inputs = jsonFile<SeasonInputsArtifact>(
    "apps/web/src/data/season-inputs.json",
  );
  const playerOdds = jsonFile<PlayerOddsArtifact>(
    "apps/web/src/data/player-odds.json",
  );
  const manual = jsonFile<ManualPriorsArtifact>(
    "apps/web/src/data/xstart-manual-priors.json",
  );
  const quoted = new Set(
    playerOdds.players.flatMap((row) =>
      typeof row.element_id === "number" ? [row.element_id] : [],
    ),
  );
  const carried = new Set(Object.keys(inputs.marketCarry?.players ?? {}));
  const manualById = new Map(manual.players.map((row) => [row.elementId, row]));
  const byClub = new Map<string, typeof inputs.players>();
  for (const player of inputs.players) {
    byClub.set(player.club, [...(byClub.get(player.club) ?? []), player]);
  }
  return {
    schemaVersion: 1,
    generatedAt: inputs.generatedAt,
    marketUpdatedAt:
      inputs.evidence?.playerMarkets?.updatedAt ?? playerOdds.fetchedAt,
    manualUpdatedAt: manual.generatedAt,
    modelVersion: modelVersion(),
    teams: [...byClub].sort().map(([club, players]) => {
      const manualKeeper = manual.players.find(
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
  const playerOdds = jsonFile<PlayerOddsArtifact>(
    "apps/web/src/data/player-odds.json",
  );
  const fixtureOdds = jsonFile<FixtureOddsArtifact>(
    "apps/web/src/data/fixture-odds.json",
  );
  return {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    modelVersion: modelVersion(),
    fixtureOdds: {
      generatedAt: fixtureOdds.generatedAt,
      season: fixtureOdds.season,
      source: fixtureOdds.source,
      fixtures: fixtureOdds.fixtures,
    },
    playerOdds: {
      fetchedAt: playerOdds.fetchedAt,
      season: playerOdds.season,
      markets: playerOdds.markets,
      quota: playerOdds.quota,
      coverage: playerOdds.coverage,
      fixtures: playerOdds.fixtures,
      players: playerOdds.players,
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
