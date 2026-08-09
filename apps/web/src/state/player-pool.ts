import { z } from "zod";

import { dedupedFetch } from "./deduped-fetch";
import {
  freshnessOf,
  LastGood,
  leastFresh,
  LIVE,
  type Freshness,
} from "./freshness";
import type { ScheduledFixture } from "./fixture-run";
import { retryingFetch } from "./retrying-fetch";
import { projectionFor, type PlayerProjection } from "./squad-projection";

/**
 * The 2026/27 player list, joined to last season's record.
 *
 * FPL publishes the new season's players, clubs and prices weeks before the
 * first deadline, which is exactly when a manager wants to know what a player
 * is worth. The prices are this season's; the record is last season's. Those
 * are two different facts and the join keeps them distinguishable rather than
 * blending them into a single invented number.
 */
const bootstrapSchema = z.object({
  elements: z.array(
    z
      .object({
        id: z.number().int().positive(),
        code: z.number().int().positive(),
        web_name: z.string().min(1),
        element_type: z.number().int().min(1).max(5),
        team: z.number().int().positive(),
        now_cost: z.number().int().positive(),
        status: z.string().min(1),
        squad_number: z.number().int().positive().max(99).nullable().optional(),
      })
      .loose(),
  ),
  element_types: z.array(
    z
      .object({
        id: z.number().int().min(1).max(5),
        singular_name_short: z.string().min(1),
      })
      .loose(),
  ),
  teams: z.array(
    z
      .object({
        id: z.number().int().positive(),
        code: z.number().int().positive(),
        short_name: z.string().min(1),
        name: z.string().min(1),
      })
      .loose(),
  ),
  events: z.array(
    z
      .object({
        id: z.number().int().min(1).max(38),
        deadline_time: z.string(),
      })
      .loose(),
  ),
});

const fixtureSchema = z.array(
  z
    .object({
      event: z.number().int().min(1).max(38).nullable(),
      team_h: z.number().int().positive(),
      team_a: z.number().int().positive(),
    })
    .loose(),
);

export interface PoolPlayer {
  elementId: number;
  code: number;
  name: string;
  position: string;
  club: string;
  teamId: number;
  /** The number on his back, where FPL has published one. */
  squadNumber: number | null;
  priceTenths: number;
  /** FPL's own availability flag: "a" is available, anything else is not. */
  available: boolean;
  /** Last season's record, or null where there is none. */
  record: PlayerProjection | null;
  /** Last season's points per match divided by this season's price. */
  perMillion: number | null;
}

export interface PlayerPool {
  players: PoolPlayer[];
  clubs: string[];
  positions: string[];
  firstDeadline: string | null;
  /** This season's club ids mapped to the code that survives a season change. */
  clubCodeByTeamId: Map<number, number>;
  fixtures: ScheduledFixture[];
  /**
   * How current this is. Never omitted, because a pool built from a retained
   * copy renders identically to a live one and a manager acts on the prices.
   */
  freshness: Freshness;
}

export function buildPlayerPool(
  payload: unknown,
  fixturePayload: unknown = [],
  freshness: Freshness = LIVE,
): PlayerPool {
  const bootstrap = bootstrapSchema.parse(payload);
  const fixtures = fixtureSchema.parse(fixturePayload);
  const positions = new Map(
    bootstrap.element_types.map((type) => [type.id, type.singular_name_short]),
  );
  const clubs = new Map(
    bootstrap.teams.map((team) => [team.id, team.short_name]),
  );

  const players = bootstrap.elements.flatMap<PoolPlayer>((element) => {
    const position = positions.get(element.element_type);
    const club = clubs.get(element.team);
    // Managers are element_type 5 and are a chip, not a footballer.
    if (!position || !club || element.element_type > 4) return [];

    const record = projectionFor(element.code);
    return [
      {
        elementId: element.id,
        code: element.code,
        name: element.web_name,
        position,
        club,
        teamId: element.team,
        squadNumber: element.squad_number ?? null,
        priceTenths: element.now_cost,
        available: element.status === "a",
        record,
        perMillion: record
          ? round(record.expectedPoints / (element.now_cost / 10))
          : null,
      },
    ];
  });

  players.sort(
    (left, right) =>
      (right.record?.expectedPoints ?? -1) -
      (left.record?.expectedPoints ?? -1),
  );

  return {
    players,
    clubs: [...new Set(players.map((player) => player.club))].sort(),
    positions: ["GKP", "DEF", "MID", "FWD"].filter((code) =>
      players.some((player) => player.position === code),
    ),
    firstDeadline:
      [...bootstrap.events].sort((left, right) => left.id - right.id).at(0)
        ?.deadline_time ?? null,
    clubCodeByTeamId: new Map(
      bootstrap.teams.map((team) => [team.id, team.code]),
    ),
    fixtures,
    freshness,
  };
}

export type PoolFailure = "unreachable" | "source_contract_failed";

export class PlayerPoolError extends Error {
  constructor(
    readonly reason: PoolFailure,
    message: string,
  ) {
    super(message);
    this.name = "PlayerPoolError";
  }
}

/**
 * The last pool that was built successfully, for the length of the tab.
 *
 * The proxy's retained copy dies with its serverless instance, so a cold start
 * during an outage still leaves the browser with nothing from that direction.
 * This is the second line: a reader who already has the list on screen does not
 * lose it because a later request failed.
 */
const lastGood = new LastGood<PlayerPool>();

/** Test seam. Production code has no reason to call this. */
export function forgetLastGoodPool(): void {
  lastGood.forget();
}

export async function fetchPlayerPool(
  fetchApi: typeof fetch = retryingFetch(),
  signal?: AbortSignal,
): Promise<PlayerPool> {
  const init = {
    headers: { Accept: "application/json" },
    signal: signal ?? null,
  };
  let bootstrap: Response;
  let fixtures: Response;
  try {
    [bootstrap, fixtures] = await Promise.all([
      dedupedFetch("/api/fpl/bootstrap-static", init, fetchApi),
      dedupedFetch("/api/fpl/fixtures", init, fetchApi),
    ]);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    return fallbackOrFail("the player list could not be requested");
  }
  if (!bootstrap.ok) {
    return fallbackOrFail(`FPL returned ${String(bootstrap.status)}`);
  }
  try {
    // A missing fixture list costs the run column and nothing else, so it is
    // not worth failing the whole page over.
    const pool = buildPlayerPool(
      await bootstrap.json(),
      fixtures.ok ? await fixtures.json() : [],
      leastFresh([
        freshnessOf(bootstrap),
        ...(fixtures.ok ? [freshnessOf(fixtures)] : []),
      ]),
    );
    // Only a live pool is worth remembering. Retaining a stale one would let
    // its age reset every time it was served back to itself.
    if (!pool.freshness.stale) lastGood.remember(pool);
    return pool;
  } catch {
    // A shape this code cannot read is not an outage, and an older pool would
    // hide a contract change that is this project's to fix.
    throw new PlayerPoolError(
      "source_contract_failed",
      "the player list did not match the expected shape",
    );
  }
}

/**
 * An older list, labelled, beats an empty page. Nothing at all is still an
 * error -- the reader is told, rather than shown a blank table.
 */
function fallbackOrFail(message: string): PlayerPool {
  const held = lastGood.recall();
  if (held) return { ...held.value, freshness: held.freshness };
  throw new PlayerPoolError("unreachable", message);
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
