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
  it("reads a career that transformed rather than a consistent one", () => {
    // Entry 1's real record. Two dreadful seasons, then elite for five.
    const profile = readManagerProfile({
      past: [
        {
          season_name: "2014/15",
          total_points: 1726,
          rank: 1_490_762,
          rank_percentage: 43,
        },
        {
          season_name: "2015/16",
          total_points: 1245,
          rank: 3_467_086,
          rank_percentage: 93,
        },
        {
          season_name: "2018/19",
          total_points: 2202,
          rank: 264_729,
          rank_percentage: 4,
        },
        {
          season_name: "2019/20",
          total_points: 2223,
          rank: 209_937,
          rank_percentage: 3,
        },
        {
          season_name: "2020/21",
          total_points: 2306,
          rank: 339_212,
          rank_percentage: 4,
        },
        {
          season_name: "2021/22",
          total_points: 2620,
          rank: 11_513,
          rank_percentage: 0.1,
        },
        {
          season_name: "2022/23",
          total_points: 2613,
          rank: 7_672,
          rank_percentage: 0.1,
        },
        {
          season_name: "2023/24",
          total_points: 2708,
          rank: 19,
          rank_percentage: 0.0,
        },
        {
          season_name: "2024/25",
          total_points: 2502,
          rank: 120_612,
          rank_percentage: 1,
        },
        {
          season_name: "2025/26",
          total_points: 2419,
          rank: 4_119,
          rank_percentage: 0.0,
        },
      ],
    });

    expect(profile?.bestRank).toBe(19);
    expect(profile?.bestPercentile).toBe(0);
    // Five seasons inside the top one percent is a pattern, never a one-off.
    expect(profile?.standoutSeasons).toBe(5);
    expect(profile?.archetype).toBe("elite");
    expect(commentary(profile!)).toMatch(/top one percent 5 times/);
  });

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
