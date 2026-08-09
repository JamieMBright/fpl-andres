import {
  EVENT_INDEX,
  PLAYABLE_START_RATE,
  SEASON_PLAYERS,
  SQUAD_SHAPE_BY_CODE,
  bestElevenPoints,
  lookaheadPointsFor,
  type SolverPlayer,
} from "./season-solver";

/**
 * The best fifteen the money can buy, for a wildcard or a free hit.
 *
 * `solveQuickPlan` is a beam search over transfers and refuses more than five a
 * week, so it cannot answer "throw the squad away and start again" -- which is
 * exactly what both these chips do. Leaving them on the published plan's weeks
 * made the chip panel advice for somebody else's team.
 *
 * This is a greedy fill by points per pound inside the real squad rules,
 * followed by bounded improvement passes: swap one held player for the best
 * affordable alternative in his position while that gains, and stop when a
 * pass changes nothing. It is not a proof of optimality and does not claim to
 * be one. It is measured against the squad it replaces, and the gain it
 * reports is the gain it actually found.
 */

const IMPROVEMENT_PASSES = 6;
const CLUB_LIMIT = 3;

export interface RebuiltSquad {
  squad: SolverPlayer[];
  /** Money left over once the fifteen is bought. */
  bankTenths: number;
}

function eligible(eventIndex: number): SolverPlayer[] {
  return SEASON_PLAYERS.filter(
    (player) =>
      player.startRate >= PLAYABLE_START_RATE &&
      lookaheadPointsFor(player, eventIndex) > 0,
  );
}

/** Squad rules, checked as the fifteen is filled rather than after. */
class SquadFrame {
  private readonly held: SolverPlayer[] = [];
  private readonly perPosition = new Map<string, number>();
  private readonly perClub = new Map<string, number>();
  private spentTenths = 0;

  get players(): SolverPlayer[] {
    return [...this.held];
  }

  get spent(): number {
    return this.spentTenths;
  }

  get size(): number {
    return this.held.length;
  }

  has(player: SolverPlayer): boolean {
    return this.held.some((member) => member.id === player.id);
  }

  /** Whether this player fits the squad rules, budget aside. */
  fits(player: SolverPlayer): boolean {
    if (this.has(player)) return false;
    const quota = SQUAD_SHAPE_BY_CODE[player.position];
    if (quota === undefined) return false;
    if ((this.perPosition.get(player.position) ?? 0) >= quota) return false;
    return (this.perClub.get(player.club) ?? 0) < CLUB_LIMIT;
  }

  filled(code: string): number {
    return this.perPosition.get(code) ?? 0;
  }

  add(player: SolverPlayer): void {
    this.held.push(player);
    this.perPosition.set(
      player.position,
      (this.perPosition.get(player.position) ?? 0) + 1,
    );
    this.perClub.set(player.club, (this.perClub.get(player.club) ?? 0) + 1);
    this.spentTenths += player.priceTenths;
  }

  remove(player: SolverPlayer): void {
    const at = this.held.findIndex((member) => member.id === player.id);
    if (at < 0) return;
    this.held.splice(at, 1);
    this.perPosition.set(
      player.position,
      (this.perPosition.get(player.position) ?? 1) - 1,
    );
    this.perClub.set(player.club, (this.perClub.get(player.club) ?? 1) - 1);
    this.spentTenths -= player.priceTenths;
  }

  /** True once every positional quota is filled. */
  complete(): boolean {
    return Object.entries(SQUAD_SHAPE_BY_CODE).every(
      ([code, quota]) => (this.perPosition.get(code) ?? 0) === quota,
    );
  }
}

/**
 * The cheapest the still-unfilled slots could possibly cost.
 *
 * Without it the greedy fill spends the budget on a strong eleven and cannot
 * afford a fifteenth player at all, which is not a legal squad. Prices are
 * pre-sorted per position and read by offset, so this stays cheap enough to
 * call on every candidate.
 */
function reserveTable(pool: SolverPlayer[]): Map<string, number[]> {
  const prices = new Map<string, number[]>();
  for (const player of pool) {
    const held = prices.get(player.position) ?? [];
    held.push(player.priceTenths);
    prices.set(player.position, held);
  }
  for (const held of prices.values()) held.sort((a, b) => a - b);
  return prices;
}

function reserveFor(frame: SquadFrame, table: Map<string, number[]>): number {
  let reserved = 0;
  for (const [code, quota] of Object.entries(SQUAD_SHAPE_BY_CODE)) {
    const filled = frame.filled(code);
    const wanted = quota - filled;
    if (wanted <= 0) continue;
    const prices = table.get(code) ?? [];
    // Skipping the first `filled` assumes the cheapest are already bought,
    // which over-reserves slightly. A squad that comes in under budget is a
    // better failure than one that cannot be completed.
    for (let index = 0; index < wanted; index += 1) {
      reserved += prices[filled + index] ?? Number.POSITIVE_INFINITY;
    }
  }
  return reserved;
}

/**
 * A fifteen bought from scratch at this gameweek.
 *
 * Scored on the lookahead, not on the week alone: a wildcard squad has to keep
 * working after the week it was bought, and picking for one Saturday is how a
 * rebuild becomes a liability three weeks later.
 */
export function rebuildSquad(
  eventIndex: number,
  budgetTenths: number,
): RebuiltSquad | null {
  const pool = eligible(eventIndex);
  if (pool.length === 0) return null;

  const value = new Map<number, number>();
  for (const player of pool) {
    value.set(player.id, lookaheadPointsFor(player, eventIndex));
  }
  const scoreOf = (player: SolverPlayer) => value.get(player.id) ?? 0;

  // Points per pound orders the fill; raw points decides an upgrade later.
  const byValue = [...pool].sort(
    (left, right) =>
      scoreOf(right) / right.priceTenths - scoreOf(left) / left.priceTenths,
  );

  const frame = new SquadFrame();
  const table = reserveTable(pool);
  for (const player of byValue) {
    if (frame.size === 15) break;
    if (!frame.fits(player)) continue;
    frame.add(player);
    // Checked after adding, because what the rest of the squad must cost
    // depends on which slot this player just took.
    if (frame.spent + reserveFor(frame, table) > budgetTenths) {
      frame.remove(player);
    }
  }
  if (!frame.complete()) return null;

  for (let pass = 0; pass < IMPROVEMENT_PASSES; pass += 1) {
    let improved = false;
    for (const held of frame.players) {
      const spare = budgetTenths - frame.spent + held.priceTenths;
      let best: SolverPlayer | null = null;
      let bestGain = 0;
      for (const candidate of pool) {
        if (candidate.position !== held.position) continue;
        if (candidate.priceTenths > spare) continue;
        const gain = scoreOf(candidate) - scoreOf(held);
        if (gain <= bestGain) continue;
        frame.remove(held);
        const fits = frame.fits(candidate);
        frame.add(held);
        if (!fits) continue;
        best = candidate;
        bestGain = gain;
      }
      if (best) {
        frame.remove(held);
        frame.add(best);
        improved = true;
      }
    }
    if (!improved) break;
  }

  return {
    squad: frame.players,
    bankTenths: budgetTenths - frame.spent,
  };
}

/**
 * What the best possible fifteen would score this week, against what is held.
 *
 * The measure both chips are chosen on: a free hit takes it for one week, a
 * wildcard keeps the squad and is priced by solving the rest of the season.
 */
export function rebuildUplift(
  event: number,
  held: readonly SolverPlayer[],
  budgetTenths: number,
): { gain: number; rebuilt: RebuiltSquad | null } {
  const eventIndex = EVENT_INDEX.get(event);
  if (eventIndex === undefined) return { gain: 0, rebuilt: null };

  const rebuilt = rebuildSquad(eventIndex, budgetTenths);
  if (!rebuilt) return { gain: 0, rebuilt: null };

  const mine = bestElevenPoints(rebuilt.squad, eventIndex);
  const theirs = bestElevenPoints([...held], eventIndex);
  return { gain: mine - theirs, rebuilt };
}
