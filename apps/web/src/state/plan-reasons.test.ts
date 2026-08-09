import { describe, expect, it } from "vitest";

import {
  chipReason,
  confidenceReason,
  fixtureReason,
  isPremium,
  moneyLines,
  moveReason,
} from "./plan-reasons";
import type { PlanGameweek, PlanPlayer } from "./season-plan";

function player(code: number, overrides: Partial<PlanPlayer> = {}): PlanPlayer {
  return {
    code,
    name: `P${String(code)}`,
    position: "MID",
    club: "ARS",
    priceTenths: 50,
    ...overrides,
  };
}

const ELEVEN = Array.from({ length: 11 }, (_, index) => player(index + 1));
const BENCH = [player(20), player(21), player(22), player(23)];

function week(overrides: Partial<PlanGameweek> = {}): PlanGameweek {
  return {
    event: 5,
    deadline: "2026-09-18T17:30:00Z",
    confidence: "projected",
    starters: ELEVEN,
    bench: BENCH,
    captain: ELEVEN[0] as PlanPlayer,
    viceCaptain: ELEVEN[1] as PlanPlayer,
    transfersIn: [],
    transfersOut: [],
    opponents: { ARS: ["CHE (H)"] },
    difficulty: { ARS: 3 },
    expected: Object.fromEntries(
      [...ELEVEN, ...BENCH].map((each) => [String(each.code), 4]),
    ),
    ceiling: Object.fromEntries(
      [...ELEVEN, ...BENCH].map((each) => [String(each.code), 9]),
    ),
    freeTransfersBefore: 1,
    paidTransfers: 0,
    transferCostPoints: 0,
    projectedPoints: 48,
    netExpectedPoints: 48,
    bankAfterTenths: 5,
    ...overrides,
  };
}

describe("moveReason", () => {
  it("says nothing more than the obvious in the opening week", () => {
    expect(moveReason(week({ event: 1 }))).toBe("Opening squad.");
  });

  it("tells you to roll rather than explaining the accounting", () => {
    expect(moveReason(week())).toContain("Roll the free transfer");
  });

  it("names both players, the gain and the fixture", () => {
    const incoming = player(30, { name: "Saka", priceTenths: 100 });
    const outgoing = player(2, { name: "Rice", priceTenths: 75 });
    const reason = moveReason(
      week({
        starters: [incoming, ...ELEVEN.slice(1)],
        transfersIn: [incoming],
        transfersOut: [outgoing],
        expected: { "30": 7, "2": 4 },
      }),
    );

    expect(reason).toContain("Rice out, Saka in");
    expect(reason).toContain("+3.0 this week");
    expect(reason).toContain("CHE (H)");
    expect(reason).toContain("£2.5m of the bank");
  });

  it("counts the hit where one is taken", () => {
    const incoming = player(30);
    const reason = moveReason(
      week({ transfersIn: [incoming], transferCostPoints: 4 }),
    );

    expect(reason).toContain("\u22124 for the extra transfers");
  });
});

describe("moneyLines", () => {
  it("gives one fact per line rather than a paragraph of figures", () => {
    const lines = moneyLines(week());

    expect(lines[0]).toContain("squad");
    expect(lines[1]).toContain("bench");
    expect(lines[2]).toContain("bank");
  });

  it("calls out a premium sitting on the bench", () => {
    const parked = player(20, { name: "Palmer", priceTenths: 95 });
    const lines = moneyLines(week({ bench: [parked, ...BENCH.slice(1)] }));

    expect(lines.join(" ")).toContain("£9.5m benched: Palmer (MID)");
  });

  it("says nothing about a cheap bench", () => {
    expect(moneyLines(week()).join(" ")).not.toContain("benched:");
  });
});

describe("isPremium", () => {
  it("uses a different line for each position", () => {
    expect(isPremium(player(1, { position: "GKP", priceTenths: 55 }))).toBe(
      true,
    );
    expect(isPremium(player(1, { position: "MID", priceTenths: 55 }))).toBe(
      false,
    );
    expect(isPremium(player(1, { position: "FWD", priceTenths: 80 }))).toBe(
      true,
    );
  });
});

describe("fixtureReason", () => {
  it("names who has the hard tie rather than hiding it in an average", () => {
    const reason = fixtureReason(
      week({
        difficulty: { ARS: 5 },
        opponents: { ARS: ["MCI (A)"] },
      }),
    );

    expect(reason).toContain("MCI (A)");
    expect(reason).toContain("four or worse");
  });

  it("says who blanks", () => {
    const reason = fixtureReason(week({ opponents: { ARS: [] } }));

    expect(reason).toContain("No fixture:");
  });

  it("withholds a rating it does not have", () => {
    expect(fixtureReason(week({ difficulty: {} }))).toBeNull();
  });
});

describe("confidenceReason", () => {
  it("leads with what is specific to the week", () => {
    const reason = confidenceReason(week());

    expect(reason.startsWith("P1 (C) is")).toBe(true);
  });

  it("argues the armband against the next best", () => {
    expect(confidenceReason(week())).toContain("Picked over");
  });

  it("flags a passenger in the eleven", () => {
    const reason = confidenceReason(
      week({ expected: { ...week().expected, "3": 1 } }),
    );

    expect(reason).toContain("Under two points:");
  });
});

describe("chipReason", () => {
  it("is honest when there is nothing to play", () => {
    expect(chipReason(null)).toBe("None this week.");
  });

  it("carries the published note", () => {
    expect(
      chipReason({
        event: 5,
        chip: "Bench Boost",
        half: "first",
        gain: 13.1,
        note: "the bench is worth 13.1",
      }),
    ).toBe("Bench Boost — the bench is worth 13.1.");
  });
});
