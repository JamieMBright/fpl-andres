import { describe, expect, it } from "vitest";

import plan from "../data/season-plan.json";
import { nearestTeletextColor, TELETEXT_PALETTE } from "./teletext";
import {
  kitForCode,
  kitForShortName,
  kitSignature,
  signatureKey,
  TEAM_KITS,
} from "./team-kits";

/**
 * These kits are hardcoded because nothing publishes them. That makes them the
 * one part of the club data with no source to drift from — so the drift shows
 * up as a missing shirt on a promoted club's players, which is invisible until
 * someone owns one.
 *
 * The first version of this file had Burnley, West Ham and Wolves in it. The
 * 2026/27 league has Coventry, Hull and Ipswich.
 */

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

  it("parses every colour it declares", () => {
    for (const kit of TEAM_KITS) {
      for (const colour of [kit.primary, kit.secondary, kit.trim]) {
        expect(() => nearestTeletextColor(colour)).not.toThrow();
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
});

describe("what the eight-colour palette costs", () => {
  it("keeps every club distinguishable", () => {
    const keys = TEAM_KITS.map((kit) => signatureKey(kitSignature(kit)));
    expect(new Set(keys).size).toBe(TEAM_KITS.length);
  });

  it("names any pair that would render identically", () => {
    const byKey = new Map<string, string[]>();
    for (const kit of TEAM_KITS) {
      const key = signatureKey(kitSignature(kit));
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

  it("separates the three red clubs on the collar alone", () => {
    const reds = ["LIV", "MUN", "NFO"].map((short) => {
      const kit = kitForShortName(short);
      if (!kit) throw new Error(`${short} has no kit`);
      return kitSignature(kit);
    });

    expect(new Set(reds.map((signature) => signature.primary)).size).toBe(1);
    expect(new Set(reds.map(signatureKey)).size).toBe(3);
  });

  it("overrides the snap only where it is stated, and to a real palette colour", () => {
    const palette = new Set(Object.keys(TELETEXT_PALETTE));
    const overridden = TEAM_KITS.filter((kit) => kit.teletext);

    // Villa's claret is the case this exists for. If the list grows, the doc
    // comment explaining why should have grown with it.
    expect(overridden.map((kit) => kit.shortName)).toEqual(["AVL"]);
    for (const kit of overridden) {
      for (const colour of Object.values(kit.teletext ?? {})) {
        expect(palette).toContain(colour);
      }
    }
  });

  it("dithers only where the palette has no name for the colour", () => {
    const dithered = TEAM_KITS.filter((kit) => kit.dither);

    // Mode 7 has no orange; Hull is the only amber club in this league.
    expect(dithered.map((kit) => kit.shortName)).toEqual(["HUL"]);
    for (const kit of dithered) {
      expect(kit.dither).toHaveLength(2);
      expect(kit.dither?.[0]).not.toBe(kit.dither?.[1]);
    }
  });
});
