import { describe, expect, it } from "vitest";

import { clubMarker, clubMarkers } from "./club-markers";
import { TEAM_KITS } from "./team-kits";

describe("club markers", () => {
  it("gives every club a mark", () => {
    expect(clubMarkers()).toHaveLength(TEAM_KITS.length);
    for (const kit of TEAM_KITS) {
      expect(clubMarker(kit.shortName), kit.shortName).not.toBeNull();
    }
  });

  it("gives no two clubs the same mark", () => {
    // Seven clubs play in red. Fill and outline alone are not enough to tell
    // them apart, which is what the dash is for.
    const marks = clubMarkers().map(
      (mark) => `${mark.fill}|${mark.stroke}|${mark.dash ?? "solid"}`,
    );

    expect(new Set(marks).size).toBe(marks.length);
  });

  it("takes the fill from the shirt", () => {
    // Arsenal play in red with white sleeves.
    expect(clubMarker("ARS")?.fill).toBe("#ff0000");
    expect(clubMarker("ARS")?.stroke).toBe("#ffffff");
  });

  it("outlines a single-colour shirt in its own colour", () => {
    // Chelsea are blue on blue. There is no accent to borrow, and inventing
    // one would say something about the kit that is not true.
    expect(clubMarker("CHE")?.fill).toBe("#0000ff");
    expect(clubMarker("CHE")?.stroke).toBe("#0000ff");
  });

  it("has nothing for a club it does not know", () => {
    expect(clubMarker("XYZ")).toBeNull();
    expect(clubMarker(null)).toBeNull();
  });
});
