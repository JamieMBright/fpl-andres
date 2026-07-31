import { describe, expect, it } from "vitest";

import {
  projectionFor,
  projectionSeason,
  squadProjection,
} from "./squad-projection";

// Bruno Fernandes. Present in every published artifact since 2019, so a stable
// anchor for the join; the assertion is on the join working, not on his number.
const KNOWN_CODE = 141746;

describe("projectionFor", () => {
  it("finds a player by the code that survives a season change", () => {
    expect(projectionFor(KNOWN_CODE)?.name).toBeTruthy();
  });

  it("returns nothing rather than guessing for an unknown player", () => {
    expect(projectionFor(1)).toBeNull();
    expect(projectionFor(undefined)).toBeNull();
  });

  it("publishes which season the record came from", () => {
    expect(projectionSeason).toMatch(/^\d{4}-\d{2}$/);
  });
});

describe("squadProjection", () => {
  it("orders the covered players by expectation", () => {
    const result = squadProjection([
      { name: "A", code: KNOWN_CODE },
      { name: "B", code: KNOWN_CODE },
    ]);

    expect(result.covered).toHaveLength(2);
    expect(result.missing).toEqual([]);
  });

  it("names the players it has no record for", () => {
    const result = squadProjection([
      { name: "Debutant", code: 999_999_999 },
      { name: "Opaque", code: undefined },
    ]);

    expect(result.missing).toEqual(["Debutant", "Opaque"]);
    expect(result.covered).toEqual([]);
  });

  it("withholds a squad total while any player is unaccounted for", () => {
    const members = Array.from({ length: 15 }, (_, index) => ({
      name: `P${index}`,
      code: index === 0 ? 999_999_999 : KNOWN_CODE,
    }));

    expect(squadProjection(members).strongestEleven).toBeNull();
  });

  it("totals the eleven strongest once every player is known", () => {
    const members = Array.from({ length: 15 }, (_, index) => ({
      name: `P${index}`,
      code: KNOWN_CODE,
    }));
    const one = projectionFor(KNOWN_CODE)?.expectedPoints ?? 0;

    expect(squadProjection(members).strongestEleven).toBeCloseTo(one * 11, 0);
  });
});
