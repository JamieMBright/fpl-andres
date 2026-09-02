import { describe, expect, it } from "vitest";

import { transferFlow, transferFlowTransitionCount } from "./transfer-flow";

describe("transfer flow", () => {
  it("has no transitions with only one captured gameweek", () => {
    expect(
      transferFlowTransitionCount({
        events: [1],
        samples: { "01": { counted: 500 } },
        holdings: { "01": [] },
      }),
    ).toBe(0);
  });

  it("reads net movement as the change in owned count between two snapshots", () => {
    const series = {
      events: [1, 2],
      samples: { "01": { counted: 500 }, "02": { counted: 500 } },
      holdings: {
        "01": [{ elementId: 1, ownedShare: 0.4, name: "Riser" }],
        "02": [
          { elementId: 1, ownedShare: 0.5, name: "Riser" },
          { elementId: 2, ownedShare: 0.02, name: "Fresh in" },
        ],
      },
    };

    const rows = transferFlow(series, 1);

    // 0.4 * 500 = 200 -> 0.5 * 500 = 250, so 50 more of the cohort hold him.
    expect(rows).toContainEqual(
      expect.objectContaining({
        elementId: 1,
        transfersIn: 50,
        transfersOut: 0,
        net: 50,
      }),
    );
    // Owned by nobody before, 10 after: entirely transfers in.
    expect(rows).toContainEqual(
      expect.objectContaining({
        elementId: 2,
        transfersIn: 10,
        transfersOut: 0,
        net: 10,
      }),
    );
  });

  it("counts a player dropped entirely as pure transfers out", () => {
    const series = {
      events: [1, 2],
      samples: { "01": { counted: 500 }, "02": { counted: 500 } },
      holdings: {
        "01": [{ elementId: 9, ownedShare: 0.06, name: "Dropped" }],
        "02": [],
      },
    };

    const rows = transferFlow(series, 1);

    expect(rows).toEqual([
      expect.objectContaining({
        elementId: 9,
        transfersIn: 0,
        transfersOut: 30,
        net: -30,
      }),
    ]);
  });

  it("sorts most transferred in first, most transferred out last", () => {
    const series = {
      events: [1, 2],
      samples: { "01": { counted: 100 }, "02": { counted: 100 } },
      holdings: {
        "01": [
          { elementId: 1, ownedShare: 0.1, name: "A" },
          { elementId: 2, ownedShare: 0.9, name: "B" },
        ],
        "02": [
          { elementId: 1, ownedShare: 0.5, name: "A" },
          { elementId: 2, ownedShare: 0.2, name: "B" },
        ],
      },
    };

    const rows = transferFlow(series, 1);

    expect(rows.map((row) => row.elementId)).toEqual([1, 2]);
  });

  it("sums movement across every transition inside the requested window", () => {
    const series = {
      events: [1, 2, 3],
      samples: {
        "01": { counted: 100 },
        "02": { counted: 100 },
        "03": { counted: 100 },
      },
      holdings: {
        "01": [{ elementId: 1, ownedShare: 0.1, name: "Climber" }],
        "02": [{ elementId: 1, ownedShare: 0.2, name: "Climber" }],
        "03": [{ elementId: 1, ownedShare: 0.35, name: "Climber" }],
      },
    };

    // Window of 1: only the most recent transition (GW2 -> GW3), +15.
    expect(transferFlow(series, 1)).toEqual([
      expect.objectContaining({ transfersIn: 15, net: 15 }),
    ]);
    // Window of 2: both transitions, +10 then +15 = +25.
    expect(transferFlow(series, 2)).toEqual([
      expect.objectContaining({ transfersIn: 25, net: 25 }),
    ]);
  });

  it("clamps a window wider than the captured history to what exists", () => {
    const series = {
      events: [1, 2],
      samples: { "01": { counted: 100 }, "02": { counted: 100 } },
      holdings: {
        "01": [{ elementId: 1, ownedShare: 0.1, name: "Only transition" }],
        "02": [{ elementId: 1, ownedShare: 0.3, name: "Only transition" }],
      },
    };

    expect(transferFlow(series, 5)).toEqual(transferFlow(series, 1));
  });

  it("returns nothing for zero or negative movement", () => {
    const series = {
      events: [1, 2],
      samples: { "01": { counted: 100 }, "02": { counted: 100 } },
      holdings: {
        "01": [{ elementId: 1, ownedShare: 0.5, name: "Steady" }],
        "02": [{ elementId: 1, ownedShare: 0.5, name: "Steady" }],
      },
    };

    expect(transferFlow(series, 1)).toEqual([]);
  });
});
