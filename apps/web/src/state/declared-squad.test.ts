import { beforeEach, describe, expect, it } from "vitest";
import { clearPrivateBrowserData } from "./private-browser-data";

import {
  declaredSquadPlanningValues,
  forgetDeclaredSquad,
  readDeclaredSquad,
  saveDeclaredSquad,
  SQUAD_BUDGET_TENTHS,
  validateDeclaredSquad,
} from "./declared-squad";
import {
  PLAYERS_BY_ELEMENT_ID,
  SEASON_EVENTS,
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

  it("keeps manager finances and optional selling prices without public provenance", () => {
    const ids = legalSquad();
    const first = ids[0]!;
    const squad = saveDeclaredSquad(
      storage,
      42,
      5,
      ids,
      PLAYERS_BY_ELEMENT_ID,
      undefined,
      {
        bankTenths: 17,
        availableFreeTransfers: 3,
        sellingPrices: [{ elementId: first, sellingPriceTenths: 35 }],
      },
    );
    expect(readDeclaredSquad(storage, 42, 5)).toEqual(squad);
    expect(squad).toMatchObject({
      version: 2,
      bankTenths: 17,
      availableFreeTransfers: 3,
      context: { season: "2026-27", rosterVersion: 1 },
    });
    expect(squad).not.toHaveProperty("stateAsOf");
    expect(declaredSquadPlanningValues(squad, 5)).toEqual({
      bankTenths: 17,
      availableFreeTransfers: 3,
      sellingPrices: new Map([[first, 35]]),
    });
    expect(declaredSquadPlanningValues(squad, 6)).toBeNull();
    expect(
      declaredSquadPlanningValues(
        { ...squad, context: { ...squad.context!, season: "2025-26" } },
        5,
      ),
    ).toBeNull();
    const changedRoster = new Map(PLAYERS_BY_ELEMENT_ID);
    changedRoster.set(first, { ...changedRoster.get(first)!, code: 999999 });
    expect(declaredSquadPlanningValues(squad, 5, changedRoster)).toBeNull();
  });

  it("loads legacy declarations for completion without inventing finances or context", () => {
    storage.setItem(
      "fpl-andres:declared-squad:v1:42:5",
      JSON.stringify({
        entryId: 42,
        event: 5,
        elementIds: legalSquad(),
        declaredAt: "2026-09-15T12:00:00Z",
      }),
    );
    const stored = readDeclaredSquad(storage, 42, 5);
    expect(stored).not.toBeNull();
    expect(stored?.bankTenths).toBeUndefined();
    expect(declaredSquadPlanningValues(stored!, 5)).toBeNull();
  });

  it("requires in-season finances and rejects invalid selling prices", () => {
    const ids = legalSquad();
    const save = (options: Parameters<typeof saveDeclaredSquad>[6]) =>
      saveDeclaredSquad(
        storage,
        42,
        5,
        ids,
        PLAYERS_BY_ELEMENT_ID,
        undefined,
        options,
      );
    expect(() => save({})).toThrow(/bank|free transfers/i);
    expect(() => save({ bankTenths: -1, availableFreeTransfers: 2 })).toThrow();
    expect(() => save({ bankTenths: 0, availableFreeTransfers: 99 })).toThrow();
    expect(() =>
      save({
        bankTenths: 0,
        availableFreeTransfers: 2,
        sellingPrices: [{ elementId: 999999, sellingPriceTenths: 35 }],
      }),
    ).toThrow();
    expect(() =>
      save({
        bankTenths: 0,
        availableFreeTransfers: 2,
        sellingPrices: [{ elementId: ids[0]!, sellingPriceTenths: 9999 }],
      }),
    ).toThrow();
    expect(readDeclaredSquad(storage, 42, 5)).toBeNull();
  });

  it("does not apply the opening budget in season", () => {
    const roster = new Map(
      POOL.map((player) => [player.id, { ...player, priceTenths: 100 }]),
    );
    expect(() =>
      saveDeclaredSquad(storage, 42, 1, legalSquad(), roster),
    ).toThrow(/Over budget/);
    expect(() =>
      saveDeclaredSquad(storage, 42, 5, legalSquad(), roster, undefined, {
        bankTenths: 0,
        availableFreeTransfers: 0,
      }),
    ).not.toThrow();
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

  it("reloads a current-event declaration as a solver start", () => {
    const event = SEASON_EVENTS[0];
    expect(event).toBeDefined();
    const initialIds = legalSquad();
    const spent = initialIds.reduce(
      (total, elementId) =>
        total + (PLAYERS_BY_ELEMENT_ID.get(elementId)?.priceTenths ?? 0),
      0,
    );
    const initial = startFromElementIds(initialIds, {
      bankTenths: SQUAD_BUDGET_TENTHS - spent,
      availableFreeTransfers: 0,
      fromEvent: event!,
    });
    expect(initial).not.toBeNull();
    saveDeclaredSquad(
      storage,
      42,
      event!,
      initialIds,
      PLAYERS_BY_ELEMENT_ID,
      () => new Date("2026-08-18T12:00:00Z"),
      { bankTenths: SQUAD_BUDGET_TENTHS - spent, availableFreeTransfers: 0 },
    );

    const reloaded = readDeclaredSquad(storage, 42, event!);
    const reloadedSpent = (reloaded?.elementIds ?? []).reduce(
      (total, elementId) =>
        total + (PLAYERS_BY_ELEMENT_ID.get(elementId)?.priceTenths ?? 0),
      0,
    );
    const restart = startFromElementIds(reloaded?.elementIds ?? [], {
      bankTenths: SQUAD_BUDGET_TENTHS - reloadedSpent,
      availableFreeTransfers: 0,
      fromEvent: event!,
    });

    expect(restart?.fromEvent).toBe(event);
    expect(solveSeason(restart!).next().value?.event).toBe(event);
  }, 30_000);

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

  it("deletes v2 finances with the existing privacy control", () => {
    saveDeclaredSquad(
      storage,
      42,
      5,
      legalSquad(),
      PLAYERS_BY_ELEMENT_ID,
      undefined,
      { bankTenths: 17, availableFreeTransfers: 3 },
    );
    clearPrivateBrowserData(storage);
    expect(readDeclaredSquad(storage, 42, 5)).toBeNull();
  });

  it("refuses unknown payload versions without treating them as legacy", () => {
    const squad = saveDeclaredSquad(storage, 42, 1, legalSquad());
    storage.setItem(
      "fpl-andres:declared-squad:v1:42:1",
      JSON.stringify({ ...squad, version: 3 }),
    );
    expect(readDeclaredSquad(storage, 42, 1)).toBeNull();
  });

  it("requires reconfirmation after the published deadline context changes", () => {
    const squad = saveDeclaredSquad(
      storage,
      42,
      5,
      legalSquad(),
      PLAYERS_BY_ELEMENT_ID,
      undefined,
      { bankTenths: 0, availableFreeTransfers: 1 },
    );
    expect(
      declaredSquadPlanningValues(
        {
          ...squad,
          context: { ...squad.context!, deadline: "2026-09-17T12:00:00Z" },
        },
        5,
      ),
    ).toBeNull();
  });
});
