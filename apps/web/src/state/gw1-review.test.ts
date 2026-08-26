import { describe, expect, it } from "vitest";

import review from "../data/gw1-review.json";
import { readGw1Review } from "./gw1-review";

describe("GW1 review artifact", () => {
  it("keeps raw points separate from the observed captain multiplier", () => {
    const parsed = readGw1Review(review);
    const raya = parsed.picks.find((pick) => pick.elementId === 1);

    expect(parsed.team).toMatchObject({ points: 56, benchPoints: 13 });
    expect(raya).toMatchObject({
      actualPoints: 6,
      band: "as_projected",
      countedPoints: 12,
      frozenXpts: 5.912784,
      isCaptain: true,
    });
  });

  it("refuses a review schema this build does not understand", () => {
    expect(() =>
      readGw1Review({ ...review, schemaVersion: review.schemaVersion + 1 }),
    ).toThrow(/schema version/i);
  });
});
