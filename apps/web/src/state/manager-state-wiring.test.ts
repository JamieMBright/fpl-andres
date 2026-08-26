import { beforeEach, describe, expect, it } from "vitest";

import { startFromElementIds, SEASON_PLAYERS } from "./season-solver";

/**
 * FPL publishes a manager's picks and his bank. It does not publish how many
 * free transfers he is holding, nor what he paid for anyone -- both are private
 * to the logged-in account. The corrections form collects them, wrote them to
 * storage, and nothing read it: every solve ran on one free transfer and a
 * squad priced at today's list.
 *
 * The list price is the wrong number twice over. A player who has risen sells
 * for his purchase price plus half the rise, so pricing him at list overstates
 * what the manager can actually raise, and the plan can propose a transfer he
 * cannot fund.
 */

beforeEach(() => {
  window.localStorage.clear();
});

const held = SEASON_PLAYERS.slice(0, 15);

describe("startFromElementIds", () => {
  it("keeps every player in a processed squad when FPL marks two doubtful", () => {
    const elementIds = [
      1, 82, 4, 388, 387, 498, 61, 346, 465, 426, 68, 481, 368, 124, 106,
    ];

    const published = new Set(SEASON_PLAYERS.map((player) => player.id));
    expect(elementIds.filter((elementId) => !published.has(elementId))).toEqual(
      [],
    );
    expect(
      startFromElementIds(elementIds, {
        bankTenths: 0,
        availableFreeTransfers: 1,
        fromEvent: 2,
      }),
    ).not.toBeNull();
  });

  it("uses the manager's own selling prices when he has given them", () => {
    const first = held[0];
    if (!first) throw new Error("no players published");
    const sellingPrices = new Map([[first.id, first.priceTenths - 3]]);

    const start = startFromElementIds(
      held.map((player) => player.id),
      {
        bankTenths: 0,
        availableFreeTransfers: 3,
        fromEvent: 2,
        sellingPrices: new Map([
          ...held.map((player) => [player.id, player.priceTenths] as const),
          ...sellingPrices,
        ]),
      },
    );

    expect(start?.squad[0]?.sellingPriceTenths).toBe(first.priceTenths - 3);
    expect(start?.availableFreeTransfers).toBe(3);
    expect(start?.assumed).toEqual([]);
  });

  it("names the list price as an assumption when he has not", () => {
    const start = startFromElementIds(
      held.map((player) => player.id),
      { bankTenths: 0, availableFreeTransfers: 1, fromEvent: 2 },
    );

    expect(start?.assumed).toContain("selling_prices");
  });

  it("carries an assumption the caller already made", () => {
    const start = startFromElementIds(
      held.map((player) => player.id),
      {
        bankTenths: 0,
        availableFreeTransfers: 1,
        fromEvent: 2,
        assumed: ["free_transfers"],
        sellingPrices: new Map(
          held.map((player) => [player.id, player.priceTenths]),
        ),
      },
    );

    expect(start?.assumed).toEqual(["free_transfers"]);
  });
});
