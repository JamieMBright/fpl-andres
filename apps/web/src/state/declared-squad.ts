import { z } from "zod";

import { PLAYERS_BY_ELEMENT_ID, type SolverPlayer } from "./season-solver";

/**
 * The fifteen a manager says he is starting the season with.
 *
 * Between seasons FPL publishes nothing: every squad is wiped, and a Team ID
 * says who you are rather than what you own. That is a real gap in the
 * evidence, not a failure, and the honest way to close it is to let the
 * manager state his own squad and label it as his claim.
 *
 * Held in `localStorage` for the same reason a declared transfer is (see
 * `declared-transfers`): a Team ID is public and enumerable, so a squad that
 * came back from a server could have been written by anybody who guessed the
 * number. In his own browser it can only ever be his claim about his own team.
 *
 * Nothing here is defaulted or repaired. A squad that breaks an FPL rule is
 * returned as the list of rules it breaks, and is never stored.
 */

const STORAGE_PREFIX = "fpl-andres:declared-squad:v1";

/** FPL squad rules, as published. Not inferred and not adjustable. */
export const SQUAD_BUDGET_TENTHS = 1000;
export const SQUAD_SIZE = 15;
export const MAX_PER_CLUB = 3;
const SHAPE: Record<SolverPlayer["position"], number> = {
  GKP: 2,
  DEF: 5,
  MID: 5,
  FWD: 3,
};
const POSITION_ORDER: SolverPlayer["position"][] = ["GKP", "DEF", "MID", "FWD"];

const declaredSquadSchema = z.object({
  entryId: z.number().int().min(1).max(4_294_967_295),
  event: z.number().int().min(1).max(47),
  elementIds: z.array(z.number().int().positive()).length(SQUAD_SIZE),
  declaredAt: z.iso.datetime(),
});

export type DeclaredSquad = z.infer<typeof declaredSquadSchema>;

export interface DeclaredSquadSummary {
  players: RosterPlayer[];
  spentTenths: number;
  bankTenths: number;
  /** Fixture-blind expected points for the best legal eleven, before captain. */
  bestElevenPoints: number;
  /** How many of the fifteen the planner holds a record for. */
  ratedCount: number;
  clubCounts: { club: string; count: number }[];
}

export type SquadValidation =
  | { valid: true; summary: DeclaredSquadSummary }
  | { valid: false; problems: string[] };

export function declaredSquadStorageKey(
  entryId: number,
  event: number,
): string {
  const parsed = declaredSquadSchema
    .pick({ entryId: true, event: true })
    .safeParse({ entryId, event });
  if (!parsed.success) {
    throw new TypeError("Team ID or gameweek is outside the supported range");
  }
  return `${STORAGE_PREFIX}:${parsed.data.entryId}:${parsed.data.event}`;
}

/**
 * Every rule the entered fifteen breaks, or the squad it adds up to.
 *
 * All problems are reported together: fixing one at a time when three are
 * wrong is the interaction this is meant to avoid.
 */
export interface RosterPlayer {
  id: number;
  name: string;
  position: string;
  club: string;
  priceTenths: number;
}

/**
 * `elementIds` are validated against `roster`, which defaults to the planning
 * pool. The builder passes the live FPL list instead: that pool carries every
 * player in the game, and a manager declaring the squad he actually picked must
 * be able to name a promoted-club debutant the planner has no record for.
 */
export function validateDeclaredSquad(
  elementIds: readonly number[],
  roster: ReadonlyMap<number, RosterPlayer> = PLAYERS_BY_ELEMENT_ID,
): SquadValidation {
  const problems: string[] = [];

  const unique = new Set(elementIds);
  if (unique.size !== elementIds.length) {
    problems.push("The same player is picked more than once.");
  }
  if (elementIds.length !== SQUAD_SIZE) {
    problems.push(
      `A squad is ${String(SQUAD_SIZE)} players; this one has ${String(elementIds.length)}.`,
    );
  }

  const players: RosterPlayer[] = [];
  const unknown: number[] = [];
  for (const elementId of unique) {
    const player = roster.get(elementId);
    if (player) players.push(player);
    else unknown.push(elementId);
  }
  if (unknown.length > 0) {
    problems.push(
      `I do not carry ${String(unknown.length)} of these players, so I will not solve around them.`,
    );
  }

  for (const position of POSITION_ORDER) {
    const held = players.filter((player) => player.position === position);
    const required = SHAPE[position];
    if (held.length !== required) {
      problems.push(
        `${position}: ${String(held.length)} picked, ${String(required)} required.`,
      );
    }
  }

  const clubCounts = countByClub(players);
  for (const { club, count } of clubCounts) {
    if (count > MAX_PER_CLUB) {
      problems.push(
        `${String(count)} players from ${club}; the limit is ${String(MAX_PER_CLUB)}.`,
      );
    }
  }

  const spentTenths = players.reduce(
    (total, player) => total + player.priceTenths,
    0,
  );
  const bankTenths = SQUAD_BUDGET_TENTHS - spentTenths;
  if (bankTenths < 0) {
    problems.push(
      `Over budget by ${(-bankTenths / 10).toFixed(1)}m of the 100.0m allowed.`,
    );
  }

  if (problems.length > 0) return { valid: false, problems };

  // Only players the planner carries can be scored. A promoted-club debutant is
  // a legal pick with no record, so he counts toward the squad and not toward
  // the eleven's points, and the shortfall is reported rather than hidden.
  const rated = players
    .map((player) => PLAYERS_BY_ELEMENT_ID.get(player.id))
    .filter((player): player is SolverPlayer => player !== undefined);

  return {
    valid: true,
    summary: {
      players,
      spentTenths,
      bankTenths,
      bestElevenPoints: bestElevenPoints(rated),
      ratedCount: rated.length,
      clubCounts,
    },
  };
}

function countByClub(
  players: readonly RosterPlayer[],
): { club: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const player of players) {
    counts.set(player.club, (counts.get(player.club) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([club, count]) => ({ club, count }))
    .sort(
      (left, right) =>
        right.count - left.count || left.club.localeCompare(right.club),
    );
}

/**
 * The best legal eleven's record points, fixture-blind.
 *
 * One keeper, at least three defenders, at least one forward, eleven in total.
 * Deliberately not a projection: it is the squad's own record, which is the
 * only thing measurable before a ball is kicked.
 */
function bestElevenPoints(players: readonly SolverPlayer[]): number {
  const byPosition = (position: SolverPlayer["position"]) =>
    players
      .filter((player) => player.position === position)
      .sort((left, right) => right.basePoints - left.basePoints);

  const keepers = byPosition("GKP");
  const defenders = byPosition("DEF");
  const midfielders = byPosition("MID");
  const forwards = byPosition("FWD");
  const first = keepers[0];
  if (!first || defenders.length < 3 || forwards.length < 1) return 0;

  const eleven = [first, ...defenders.slice(0, 3), ...forwards.slice(0, 1)];
  const remainder = [
    ...defenders.slice(3),
    ...midfielders,
    ...forwards.slice(1),
  ].sort((left, right) => right.basePoints - left.basePoints);

  for (const player of remainder) {
    if (eleven.length === 11) break;
    eleven.push(player);
  }
  return eleven.reduce((total, player) => total + player.basePoints, 0);
}

export function saveDeclaredSquad(
  storage: Storage,
  entryId: number,
  event: number,
  elementIds: readonly number[],
  roster: ReadonlyMap<number, RosterPlayer> = PLAYERS_BY_ELEMENT_ID,
  now: () => Date = () => new Date(),
): DeclaredSquad {
  const validation = validateDeclaredSquad(elementIds, roster);
  if (!validation.valid) {
    throw new TypeError(validation.problems.join(" "));
  }
  const squad = declaredSquadSchema.parse({
    entryId,
    event,
    elementIds: [...elementIds],
    declaredAt: now().toISOString(),
  });
  storage.setItem(
    declaredSquadStorageKey(entryId, event),
    JSON.stringify(squad),
  );
  return squad;
}

/**
 * A stored squad that no longer parses is discarded.
 *
 * Legality is deliberately NOT re-checked here. The squad was checked against
 * the live FPL list when it was saved, and this reader is often called before
 * that list has loaded -- re-checking against the smaller planning pool wiped
 * every squad containing a player the planner holds no record for.
 */
export function readDeclaredSquad(
  storage: Storage,
  entryId: number,
  event: number,
): DeclaredSquad | null {
  const key = declaredSquadStorageKey(entryId, event);
  const serialized = storage.getItem(key);
  if (serialized === null) return null;

  try {
    const parsed = declaredSquadSchema.safeParse(JSON.parse(serialized));
    if (
      !parsed.success ||
      parsed.data.entryId !== entryId ||
      parsed.data.event !== event ||
      parsed.data.elementIds.length !== SQUAD_SIZE ||
      new Set(parsed.data.elementIds).size !== SQUAD_SIZE
    ) {
      storage.removeItem(key);
      return null;
    }
    return parsed.data;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

export function forgetDeclaredSquad(
  storage: Storage,
  entryId: number,
  event: number,
): void {
  storage.removeItem(declaredSquadStorageKey(entryId, event));
}
