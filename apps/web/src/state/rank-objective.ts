import { z } from "zod";

/**
 * Which race the plan is being solved for.
 *
 * Climbing a mini-league and climbing the overall rank are not the same
 * optimisation and they routinely disagree. Overall rank is a contest against
 * eleven million squads, so the field's ownership is close to the average and
 * the best you can do is take the highest expected points on offer. A
 * mini-league is a contest against a dozen named people whose squads you can
 * read, and there the variance is the whole game: a player nine of your twelve
 * rivals own is a threat whether or not he is a good buy, and a player none of
 * them own is a lever whether or not he is the best available.
 *
 * So the plan has to ask. It cannot be inferred and defaulting it silently
 * would give half the readers the wrong advice with no way to tell.
 *
 * Held in `localStorage` for the same reason as the declared transfers and
 * chips beside it: a Team ID is public and enumerable, so anything a server
 * handed back could have been typed by somebody else.
 */

const STORAGE_PREFIX = "fpl-andres:objective:v1";

export const OBJECTIVES = ["overall", "league"] as const;

export type Objective = (typeof OBJECTIVES)[number];

export const OBJECTIVE_NAMES: Record<Objective, string> = {
  overall: "Overall rank",
  league: "A mini-league",
};

const objectiveSchema = z.enum(OBJECTIVES);

const rankObjectiveSchema = z.object({
  objective: objectiveSchema,
  /** The league being chased. Null while the objective is overall rank. */
  leagueId: z.number().int().min(1).max(4_294_967_295).nullable().default(null),
});

export type RankObjective = z.infer<typeof rankObjectiveSchema>;

/**
 * Unanswered, not "overall".
 *
 * The plan withholds a mini-league reading until it is told, rather than
 * assuming the commoner answer and being quietly wrong for everyone else.
 */
export const NO_OBJECTIVE: RankObjective = {
  objective: "overall",
  leagueId: null,
};

function key(entryId: number): string {
  return `${STORAGE_PREFIX}:${entryId}`;
}

export function readRankObjective(
  storage: Storage,
  entryId: number,
): RankObjective | null {
  const raw = storage.getItem(key(entryId));
  if (!raw) return null;
  try {
    const parsed = rankObjectiveSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) {
      storage.removeItem(key(entryId));
      return null;
    }
    return parsed.data;
  } catch {
    storage.removeItem(key(entryId));
    return null;
  }
}

export function saveRankObjective(
  storage: Storage,
  entryId: number,
  chosen: RankObjective,
): RankObjective {
  // A league id only means anything against the league objective, and keeping
  // one behind an overall answer would let a later re-read resurrect it.
  const next: RankObjective = {
    objective: chosen.objective,
    leagueId: chosen.objective === "league" ? chosen.leagueId : null,
  };
  storage.setItem(key(entryId), JSON.stringify(next));
  return next;
}

export function forgetRankObjective(storage: Storage, entryId: number): void {
  storage.removeItem(key(entryId));
}

/** True where the answer is complete enough to read a league with. */
export function chasesLeague(
  chosen: RankObjective | null,
): chosen is RankObjective & { leagueId: number } {
  return chosen?.objective === "league" && chosen.leagueId !== null;
}
