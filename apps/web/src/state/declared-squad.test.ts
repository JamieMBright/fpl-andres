import { beforeEach, describe, expect, it } from "vitest";

import {
  forgetDeclaredSquad,
  readDeclaredSquad,
  saveDeclaredSquad,
  SQUAD_BUDGET_TENTHS,
  validateDeclaredSquad,
} from "./declared-squad";
import {
  PLAYERS_BY_ELEMENT_ID,
  solveSeason,
  startFromElementIds,
  type SolverPlayer,
} from "./season-solver";

/**
 * Before the first deadline FPL publishes nothing, so a manager's own claim is
 * the only squad there is. These pin that the claim is checked against the
 * real rules rather than defaulted, and that a broken one is never stored.
 */

function memoryStorage(): Storage {
  const held = new Map<string, string>();
  return {
    get length() {
      return held.size;
    },
    clear: () => held.clear(),
    getItem: (key) => held.get(key) ?? null,
    key: (index) => [...held.keys()][index] ?? null,
    removeItem: (key) => held.delete(key),
    setItem: (key, value) => held.set(key, value),
  } as Storage;
}

const POOL = [...PLAYERS_BY_ELEMENT_ID.values()];

function cheapest(
  position: SolverPlayer["position"],
  count: number,
  exclude: ReadonlySet<number> = new Set(),
): SolverPlayer[] {
  return POOL.filter(
    (player) => player.position === position && !exclude.has(player.id),
  )
    .sort((left, right) => left.priceTenths - right.priceTenths)
    .slice(0, count);
}

/** A legal fifteen: right shape, inside the budget, no club over three. */
function legalSquad(): number[] {
  const picked: SolverPlayer[] = [];
  const clubCounts = new Map<string, number>();
  const shape: [SolverPlayer["position"], number][] = [
    ["GKP", 2],
    ["DEF", 5],
    ["MID", 5],
    ["FWD", 3],
  ];
  for (const [position, required] of shape) {
    const candidates = POOL.filter(
      (player) => player.position === position,
    ).sort((left, right) => left.priceTenths - right.priceTenths);
    let taken = 0;
    for (const candidate of candidates) {
      if (taken === required) break;
      const held = clubCounts.get(candidate.club) ?? 0;
      if (held >= 3) continue;
      clubCounts.set(candidate.club, held + 1);
      picked.push(candidate);
      taken += 1;
    }
  }
  return picked.map((player) => player.id);
}

describe("declared squad", () => {
  let storage: Storage;

  beforeEach(() => {
    storage = memoryStorage();
  });

  it("accepts a squad that obeys every published rule", () => {
    const validation = validateDeclaredSquad(legalSquad());

    expect(validation.valid).toBe(true);
    if (!validation.valid) return;
    expect(validation.summary.players).toHaveLength(15);
    expect(validation.summary.bankTenths).toBeGreaterThanOrEqual(0);
    expect(validation.summary.bestElevenPoints).toBeGreaterThan(0);
  });

  it("reports every broken rule at once rather than one at a time", () => {
    const validation = validateDeclaredSquad(
      cheapest("MID", 15).map((player) => player.id),
    );

    expect(validation.valid).toBe(false);
    if (validation.valid) return;
    expect(validation.problems.length).toBeGreaterThan(1);
    expect(validation.problems.join(" ")).toContain("GKP");
  });

  it("refuses a squad holding a player it does not carry", () => {
    const squad = legalSquad();
    squad[0] = 99_999_999;

    const validation = validateDeclaredSquad(squad);

    expect(validation.valid).toBe(false);
  });

  it("refuses a squad over the hundred million budget", () => {
    const dearest = (position: SolverPlayer["position"], count: number) =>
      POOL.filter((player) => player.position === position)
        .sort((left, right) => right.priceTenths - left.priceTenths)
        .slice(0, count);
    const squad = [
      ...dearest("GKP", 2),
      ...dearest("DEF", 5),
      ...dearest("MID", 5),
      ...dearest("FWD", 3),
    ].map((player) => player.id);

    const validation = validateDeclaredSquad(squad);

    expect(validation.valid).toBe(false);
    if (validation.valid) return;
    expect(validation.problems.join(" ")).toContain("Over budget");
  });

  it("stores and reads back a legal squad for one team and gameweek", () => {
    const squad = legalSquad();

    saveDeclaredSquad(storage, 42, 1, squad);

    expect(readDeclaredSquad(storage, 42, 1)?.elementIds).toEqual(squad);
    expect(readDeclaredSquad(storage, 43, 1)).toBeNull();
    expect(readDeclaredSquad(storage, 42, 2)).toBeNull();
  });

  it("stores an accepted opening recommendation with the complete fifteen", () => {
    const squad = legalSquad();

    saveDeclaredSquad(
      storage,
      42,
      1,
      squad,
      PLAYERS_BY_ELEMENT_ID,
      () => new Date("2026-08-18T12:00:00Z"),
      { openingDecision: "accepted" },
    );

    expect(readDeclaredSquad(storage, 42, 1)).toMatchObject({
      elementIds: squad,
      openingDecision: "accepted",
    });
  });

  it("clears an opening lock when the manager later edits the squad", () => {
    const squad = legalSquad();
    saveDeclaredSquad(
      storage,
      42,
      1,
      squad,
      PLAYERS_BY_ELEMENT_ID,
      () => new Date("2026-08-18T12:00:00Z"),
      { openingDecision: "held" },
    );

    saveDeclaredSquad(storage, 42, 1, squad);

    expect(readDeclaredSquad(storage, 42, 1)?.openingDecision).toBeUndefined();
  });

  it("reloads an accepted recommendation as a locked GW1 fixpoint", () => {
    const initialIds = legalSquad();
    const spent = initialIds.reduce(
      (total, elementId) =>
        total + (PLAYERS_BY_ELEMENT_ID.get(elementId)?.priceTenths ?? 0),
      0,
    );
    const initial = startFromElementIds(initialIds, {
      bankTenths: SQUAD_BUDGET_TENTHS - spent,
      availableFreeTransfers: 0,
      fromEvent: 1,
    });
    expect(initial).not.toBeNull();
    const recommended = solveSeason(initial!).next().value;
    expect(recommended?.transfersIn.length).toBeGreaterThan(0);
    const acceptedIds = [
      ...(recommended?.starters ?? []),
      ...(recommended?.bench ?? []),
    ].map((player) => player.id);
    saveDeclaredSquad(
      storage,
      42,
      1,
      acceptedIds,
      PLAYERS_BY_ELEMENT_ID,
      () => new Date("2026-08-18T12:00:00Z"),
      { openingDecision: "accepted" },
    );

    const reloaded = readDeclaredSquad(storage, 42, 1);
    const reloadedSpent = (reloaded?.elementIds ?? []).reduce(
      (total, elementId) =>
        total + (PLAYERS_BY_ELEMENT_ID.get(elementId)?.priceTenths ?? 0),
      0,
    );
    const restart = startFromElementIds(reloaded?.elementIds ?? [], {
      bankTenths: SQUAD_BUDGET_TENTHS - reloadedSpent,
      availableFreeTransfers: 0,
      fromEvent: 1,
    });
    expect(restart).not.toBeNull();
    const locked = solveSeason({ ...restart!, lockOpening: true }).next().value;

    expect(locked?.transfersIn).toEqual([]);
    expect(locked?.transfersOut).toEqual([]);
    expect(
      [...(locked?.starters ?? []), ...(locked?.bench ?? [])]
        .map((player) => player.id)
        .sort((left, right) => left - right),
    ).toEqual([...acceptedIds].sort((left, right) => left - right));
  });

  it("never stores a squad that breaks a rule", () => {
    expect(() => saveDeclaredSquad(storage, 42, 1, [1, 2, 3])).toThrow(
      TypeError,
    );
    expect(readDeclaredSquad(storage, 42, 1)).toBeNull();
  });

  it("discards a stored squad that no longer obeys the rules", () => {
    saveDeclaredSquad(storage, 42, 1, legalSquad());
    const key = "fpl-andres:declared-squad:v1:42:1";
    const stored = JSON.parse(storage.getItem(key) ?? "{}") as {
      elementIds: number[];
    };
    stored.elementIds[0] = stored.elementIds[1] ?? 0;
    storage.setItem(key, JSON.stringify(stored));

    expect(readDeclaredSquad(storage, 42, 1)).toBeNull();
    expect(storage.getItem(key)).toBeNull();
  });

  it("forgets a squad on request", () => {
    saveDeclaredSquad(storage, 42, 1, legalSquad());

    forgetDeclaredSquad(storage, 42, 1);

    expect(readDeclaredSquad(storage, 42, 1)).toBeNull();
  });
});
