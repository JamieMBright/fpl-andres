import { describe, expect, it } from "vitest";

import {
  marketIsSilent,
  marketReach,
  marketSentence,
  type MarketReach,
} from "./market-reach";

/**
 * The method page described a bookmaker's contribution in the present tense
 * while the ingestion had never produced a file. A page that claims a source it
 * is not reading is the same failure as a verdict drifting from its table, so
 * the claim is derived and these fail if it stops matching.
 */

function reach(over: Partial<MarketReach> = {}): MarketReach {
  return {
    attackingRoutes: 0,
    playersQuoted: 0,
    cardRoutes: 0,
    playersQuotedForCards: 0,
    shotRoutes: 0,
    playersQuotedForShots: 0,
    startRatesCut: 0,
    participationInferred: 0,
    squadsNamed: 0,
    fixtureRungs: 0,
    bonusEvents: 0,
    ...over,
  };
}

describe("what the market actually moved", () => {
  it("reads the shipped artifact without throwing", () => {
    const shipped = marketReach();

    expect(shipped.attackingRoutes).toBeGreaterThanOrEqual(0);
    expect(shipped.fixtureRungs).toBeGreaterThanOrEqual(0);
  });

  it("calls it silent when nothing was priced", () => {
    expect(marketIsSilent(reach())).toBe(true);
  });

  it("does not call it silent on a single blended route", () => {
    expect(marketIsSilent(reach({ attackingRoutes: 1 }))).toBe(false);
    expect(marketIsSilent(reach({ cardRoutes: 1 }))).toBe(false);
    expect(marketIsSilent(reach({ shotRoutes: 1 }))).toBe(false);
    expect(marketIsSilent(reach({ startRatesCut: 1 }))).toBe(false);
    expect(marketIsSilent(reach({ participationInferred: 1 }))).toBe(false);
    expect(marketIsSilent(reach({ fixtureRungs: 1 }))).toBe(false);
    expect(marketIsSilent(reach({ bonusEvents: 1 }))).toBe(false);
  });

  it("says plainly that nothing is switched on rather than describing the plan", () => {
    const said = marketSentence(reach());

    expect(said).toContain("None of it is switched on");
    expect(said).toContain("the record alone");
  });

  it("counts what a live run moved", () => {
    const said = marketSentence(
      reach({
        attackingRoutes: 240,
        playersQuoted: 300,
        cardRoutes: 90,
        shotRoutes: 40,
        playersQuotedForShots: 55,
        participationInferred: 12,
        fixtureRungs: 10,
        bonusEvents: 8,
      }),
    );

    expect(said).toContain("240 attacking routes from 300 players quoted");
    expect(said).toContain("90 card routes");
    expect(said).toContain("40 shot routes from 55 players quoted");
    expect(said).toContain("12 participation estimates");
    expect(said).toContain("10 fixture rungs");
    expect(said).toContain("8 BPS-ranked bonus events");
    expect(said).not.toContain("switched on");
  });

  it("leaves out the halves that moved nothing", () => {
    const said = marketSentence(reach({ fixtureRungs: 10 }));

    expect(said).toContain("10 fixture rungs");
    expect(said).not.toContain("attacking routes");
    expect(said).not.toContain("card routes");
  });
});
