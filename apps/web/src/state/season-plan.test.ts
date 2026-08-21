import { describe, expect, it } from "vitest";

import { pairTransfers, type PlanPlayer } from "./season-plan";

function player(
  code: number,
  position: string,
  name = `P${String(code)}`,
): PlanPlayer {
  return { code, name, position, club: "ARS", priceTenths: 50 };
}

describe("pairing a week's transfers", () => {
  it("matches each player out with the player in who replaced him", () => {
    // The reported bug: the solver listed the keeper first going out and the
    // defender first coming in, so the page read "keeper out, defender in".
    const out = [player(1, "GKP", "Raya"), player(2, "DEF", "Gabriel")];
    const incoming = [player(3, "DEF", "Saliba"), player(4, "GKP", "Sels")];

    expect(pairTransfers(out, incoming)).toEqual([
      { out: out[0], in: incoming[1] },
      { out: out[1], in: incoming[0] },
    ]);
  });

  it("keeps like for like when several of one position move at once", () => {
    const out = [player(1, "MID"), player(2, "DEF"), player(3, "MID")];
    const incoming = [player(4, "MID"), player(5, "MID"), player(6, "DEF")];

    const swaps = pairTransfers(out, incoming);

    for (const swap of swaps) {
      expect(swap.in.position).toBe(swap.out.position);
    }
    expect(swaps).toHaveLength(3);
  });

  it("uses every player exactly once", () => {
    const out = [player(1, "FWD"), player(2, "DEF")];
    const incoming = [player(3, "DEF"), player(4, "FWD")];

    const swaps = pairTransfers(out, incoming);

    expect(new Set(swaps.map((swap) => swap.in.code)).size).toBe(2);
    expect(new Set(swaps.map((swap) => swap.out.code)).size).toBe(2);
  });

  it("shows nothing when nothing moved", () => {
    expect(pairTransfers([], [])).toEqual([]);
  });

  it("still shows a move if the squad shape ever failed to balance", () => {
    // Not reachable from a legal plan, but dropping a transfer off the page
    // would hide a decision rather than report a fault.
    const out = [player(1, "GKP")];
    const incoming = [player(2, "FWD")];

    expect(pairTransfers(out, incoming)).toEqual([
      { out: out[0], in: incoming[0] },
    ]);
  });
});
