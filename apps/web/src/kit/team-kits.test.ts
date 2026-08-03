import { describe, expect, it } from "vitest";

import plan from "../data/season-plan.json";
import {
  kitForCode,
  kitForShortName,
  signatureKey,
  TEAM_KITS,
} from "./team-kits";
import { TELETEXT_PALETTE } from "./teletext";

/**
 * These kits are hardcoded because nothing publishes them. That makes them the
 * one part of the club data with no source to drift from — so the drift shows
 * up as a missing shirt on a promoted club's players, which is invisible until
 * someone owns one.
 *
 * The first version of this file had Burnley, West Ham and Wolves in it. The
 * 2026/27 league has Coventry, Hull and Ipswich.
 */

const PALETTE = new Set(Object.keys(TELETEXT_PALETTE));

function coloursOf(kit: (typeof TEAM_KITS)[number]): string[] {
  const { paint } = kit;
  return [
    paint.base,
    paint.sleeves,
    ...paint.collar,
    ...(paint.collarDither ?? []),
    ...(paint.stripes ?? []),
    ...(paint.hoops ?? []),
    ...(paint.sash ?? []),
    ...(paint.shoulder ?? []),
    ...(paint.cuffs ?? []),
    ...(paint.sideLine ? [paint.sideLine] : []),
    ...(paint.fade ? [paint.fade.from, paint.fade.to] : []),
    ...(paint.collarNotch ? [paint.collarNotch.colour] : []),
  ];
}

describe("the kit list", () => {
  it("has exactly the twenty clubs, keyed uniquely", () => {
    expect(TEAM_KITS).toHaveLength(20);
    expect(new Set(TEAM_KITS.map((kit) => kit.code)).size).toBe(20);
    expect(new Set(TEAM_KITS.map((kit) => kit.shortName)).size).toBe(20);
  });

  it("covers every club the published season plan actually names", () => {
    const clubs = new Set(
      Object.values(plan.players).map((player) => player.club),
    );

    expect(clubs.size).toBeGreaterThan(0);
    for (const club of clubs) {
      expect(kitForShortName(club), `no kit for ${club}`).not.toBeNull();
    }
  });

  it("uses only colours a teletext page had", () => {
    for (const kit of TEAM_KITS) {
      for (const colour of coloursOf(kit)) {
        expect(PALETTE, `${kit.shortName} uses ${colour}`).toContain(colour);
      }
    }
  });

  it("looks up by code and by short name to the same club", () => {
    for (const kit of TEAM_KITS) {
      expect(kitForCode(kit.code)).toEqual(kit);
      expect(kitForShortName(kit.shortName)).toEqual(kit);
    }
    expect(kitForCode(null)).toBeNull();
    expect(kitForCode(999999)).toBeNull();
    expect(kitForShortName("ZZZ")).toBeNull();
  });

  it("gives every kit a collar, because a bare neck reads as unfinished", () => {
    for (const kit of TEAM_KITS) {
      expect(kit.paint.collar.length, kit.shortName).toBeGreaterThan(0);
    }
  });
});

describe("what the eight-colour palette costs", () => {
  it("keeps every club distinguishable", () => {
    const keys = TEAM_KITS.map(signatureKey);
    expect(new Set(keys).size).toBe(TEAM_KITS.length);
  });

  it("names any pair that would render identically", () => {
    const byKey = new Map<string, string[]>();
    for (const kit of TEAM_KITS) {
      const key = signatureKey(kit);
      byKey.set(key, [...(byKey.get(key) ?? []), kit.shortName]);
    }

    const collisions = [...byKey.values()]
      .filter((clubs) => clubs.length > 1)
      .map((clubs) => clubs.sort().join("+"))
      .sort();

    // Pinned empty. Losing a club to a collision is a regression in how much
    // the shirt tells you, and should have to be argued for.
    expect(collisions).toEqual([]);
  });

  it("separates the red clubs on details rather than on colour", () => {
    const reds = ["ARS", "BOU", "BRE", "LIV", "MUN", "NFO", "SUN"].map(
      (short) => {
        const kit = kitForShortName(short);
        if (!kit) throw new Error(`${short} has no kit`);
        return kit;
      },
    );

    // Every one of them is a red shirt. Seven of twenty.
    expect(new Set(reds.map((kit) => kit.paint.base))).toEqual(
      new Set(["red"]),
    );
    expect(new Set(reds.map(signatureKey)).size).toBe(reds.length);
  });
});
