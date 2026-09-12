import { describe, expect, it } from "vitest";

import {
  reconcileTeamSellingPrices,
  sellingPriceTenths,
} from "../../../../api/_lib/team-price";

describe("FPL selling prices", () => {
  it("keeps half of a price rise, rounded down", () => {
    const rules = { sellAtPurchasePrice: false };
    expect(sellingPriceTenths(70, 74, rules)).toBe(72);
    expect(sellingPriceTenths(70, 73, rules)).toBe(71);
    expect(sellingPriceTenths(70, 68, rules)).toBe(68);
  });

  it("uses the latest public purchase cost and reconciles team value", () => {
    const prices = reconcileTeamSellingPrices(
      [{ element: 1 }, { element: 2 }],
      [
        { id: 1, nowCost: 74, costChangeStart: 4 },
        { id: 2, nowCost: 60, costChangeStart: 0 },
      ],
      [
        {
          elementIn: 1,
          elementInCost: 70,
          event: 3,
          time: "2026-08-30T12:00:00Z",
        },
      ],
      6,
      138,
      { sellAtPurchasePrice: false },
    );

    expect(prices).toEqual(
      new Map([
        [1, { purchasePriceTenths: 70, sellingPriceTenths: 72 }],
        [2, { purchasePriceTenths: 60, sellingPriceTenths: 60 }],
      ]),
    );
  });

  it("fails closed when per-player prices do not reconcile", () => {
    expect(
      reconcileTeamSellingPrices(
        [{ element: 1 }],
        [{ id: 1, nowCost: 74, costChangeStart: 4 }],
        [],
        0,
        74,
        { sellAtPurchasePrice: false },
      ),
    ).toBeNull();
  });

  it("honors a source rule that sells at purchase price", () => {
    const prices = reconcileTeamSellingPrices(
      [{ element: 1 }],
      [{ id: 1, nowCost: 74, costChangeStart: 4 }],
      [
        {
          elementIn: 1,
          elementInCost: 70,
          event: 3,
          time: "2026-08-30T12:00:00Z",
        },
      ],
      0,
      70,
      { sellAtPurchasePrice: true },
    );

    expect(prices?.get(1)?.sellingPriceTenths).toBe(70);
  });
});
