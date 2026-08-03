import { describe, expect, it } from "vitest";

import { bandFor } from "./stat-bands";

/**
 * The bands come from the published pool's own quartiles per position, so these
 * check the shape of the answer rather than pinning numbers that move whenever
 * the projections are regenerated.
 */
describe("bandFor", () => {
  it("has no opinion about a missing figure", () => {
    expect(bandFor("MID", "expectedPoints", null)).toBeNull();
  });

  it("rates a huge figure as the best of its position", () => {
    expect(bandFor("DEF", "expectedPoints", 99)).toBe("strong");
  });

  it("rates a zero as below most of its position", () => {
    expect(bandFor("DEF", "expectedPoints", 0)).toBe("poor");
  });

  it("turns the scale around where a bigger number is worse", () => {
    // Blanking often is bad, so a high blank rate must not read as strong.
    expect(bandFor("MID", "blankRate", 1)).toBe("poor");
    expect(bandFor("MID", "blankRate", 0)).toBe("strong");
  });

  it("judges a figure against its own position, not the whole game", () => {
    // The same points-per-match reads differently by position, so somewhere on
    // the scale a keeper and a forward must disagree about the same number.
    const disagrees = [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].some(
      (value) =>
        bandFor("GKP", "expectedPoints", value) !==
        bandFor("FWD", "expectedPoints", value),
    );

    expect(disagrees).toBe(true);
  });

  it("says nothing about a position it has too few players for", () => {
    expect(bandFor("NOT_A_POSITION", "expectedPoints", 5)).toBeNull();
  });
});
