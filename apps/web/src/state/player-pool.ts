import { z } from "zod";

import type { ScheduledFixture } from "./fixture-run";
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
}

export function buildPlayerPool(
  payload: unknown,
  fixturePayload: unknown = [],
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
  };
}

export async function fetchPlayerPool(
  fetchApi: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<PlayerPool> {
  const init = {
    headers: { Accept: "application/json" },
    signal: signal ?? null,
  };
  const [bootstrap, fixtures] = await Promise.all([
    fetchApi("/api/fpl/bootstrap-static/", init),
    fetchApi("/api/fpl/fixtures/", init),
  ]);
  if (!bootstrap.ok) {
    throw new Error(`FPL returned ${bootstrap.status}`);
  }
  // A missing fixture list costs the run column and nothing else, so it is not
  // worth failing the whole page over.
  return buildPlayerPool(
    await bootstrap.json(),
    fixtures.ok ? await fixtures.json() : [],
  );
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
