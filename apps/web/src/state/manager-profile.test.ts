import { describe, expect, it } from "vitest";

import { commentary, readManagerProfile } from "./manager-profile";

function history(entries: [string, number, number | null][]) {
  return {
    past: entries.map(([season_name, total_points, rank]) => ({
      season_name,
      total_points,
      rank,
    })),
  };
}

describe("readManagerProfile", () => {
  it("drops seasons that were never completed rather than scoring them", () => {
    const profile = readManagerProfile(
      history([
        ["2023/24", 2400, 50_000],
        ["2024/25", 0, null],
        ["2025/26", 2350, 80_000],
      ]),
    );

    expect(profile?.seasonsPlayed).toBe(2);
    expect(profile?.bestRank).toBe(50_000);
  });

  it("names the season the best finish came in", () => {
    const profile = readManagerProfile(
      history([
        ["2022/23", 2500, 900_000],
        ["2023/24", 2600, 12_000],
        ["2024/25", 2400, 700_000],
      ]),
    );

    expect(profile?.bestSeason).toBe("2023/24");
  });

  it("calls a consistently elite record a contender", () => {
    const profile = readManagerProfile(
      history([
        ["2022/23", 2600, 40_000],
        ["2023/24", 2650, 30_000],
        ["2024/25", 2620, 60_000],
        ["2025/26", 2700, 20_000],
      ]),
    );

    expect(profile?.archetype).toBe("contender");
  });

  it("calls one great season among ordinary ones a spike", () => {
    const profile = readManagerProfile(
      history([
        ["2021/22", 2200, 1_400_000],
        ["2022/23", 2700, 8_000],
        ["2023/24", 2100, 2_000_000],
        ["2024/25", 2150, 1_800_000],
      ]),
    );

    expect(profile?.archetype).toBe("spiker");
    expect(commentary(profile!)).toMatch(/mostly variance/i);
  });

  it("spots an improving career", () => {
    const profile = readManagerProfile(
      history([
        ["2022/23", 2000, 3_000_000],
        ["2023/24", 2100, 2_500_000],
        ["2024/25", 2400, 900_000],
        ["2025/26", 2450, 700_000],
      ]),
    );

    expect(profile?.archetype).toBe("climber");
    expect(profile?.trend).toBeLessThan(0);
  });

  it("spots a declining one and says so plainly", () => {
    const profile = readManagerProfile(
      history([
        ["2022/23", 2500, 200_000],
        ["2023/24", 2450, 400_000],
        ["2024/25", 2200, 2_000_000],
        ["2025/26", 2150, 2_500_000],
      ]),
    );

    expect(profile?.archetype).toBe("fader");
    expect(commentary(profile!)).toMatch(/worse than where you started/i);
  });

  it("does not read a direction into a short career", () => {
    const profile = readManagerProfile(
      history([
        ["2024/25", 2300, 500_000],
        ["2025/26", 2400, 300_000],
      ]),
    );

    expect(profile?.trend).toBeNull();
    expect(profile?.archetype).toBe("newcomer");
  });

  it("returns nothing when there is no completed season", () => {
    expect(readManagerProfile(history([["2025/26", 0, null]]))).toBeNull();
    expect(readManagerProfile({ past: [] })).toBeNull();
    expect(readManagerProfile({ nonsense: true })).toBeNull();
  });

  it("refuses a malformed payload rather than guessing", () => {
    expect(readManagerProfile({ past: [{ season_name: "nope" }] })).toBeNull();
  });
});
