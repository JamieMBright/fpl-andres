import { describe, expect, it } from "vitest";

import validation from "../data/validation.json";
import {
  leagueVerdict,
  pooledVerdict,
  positionVerdict,
  rankBandClass,
  rankPerformanceLabel,
  separableVerdict,
  type LeagueSeason,
  type VerdictSeason,
} from "./validation-verdict";

/**
 * The page's prose has to agree with the page's numbers.
 *
 * It did not. The calibration page stated that the naive last-five average
 * "ranks better than my projection in every season I tested" while the artifact
 * beside it had the model ahead on rank correlation, mean absolute error and
 * top-20 hit rate in all four seasons. A hand-written verdict is a claim nobody
 * re-checks, and this one had been wrong long enough for the owner to believe
 * the model was losing.
 */

const POSITIONS = ["GKP", "DEF", "MID", "FWD"];
const seasons = (validation as { seasons: unknown[] })
  .seasons as VerdictSeason[];

function methodOf(season: VerdictSeason, label: string) {
  return season.methods.find((method) => method.label === label);
}

describe("the shipped artifact", () => {
  it("is what the pooled verdict describes", () => {
    const measured = seasons.filter((season) => {
      const mine = methodOf(season, "model")?.spearman ?? null;
      const naive = methodOf(season, "recent_mean")?.spearman ?? null;
      return mine !== null && naive !== null && mine > naive;
    }).length;

    const verdict = pooledVerdict(seasons);
    expect(verdict.modelWins).toBe(measured);
    expect(verdict.seasons).toBe(seasons.length);
    // Whichever way the artifact falls, the sentence has to name it.
    expect(verdict.sentence).toContain(String(verdict.seasons));
  });

  it("is what the per-position verdict describes", () => {
    const verdict = positionVerdict(seasons, POSITIONS);
    expect(verdict.cells).toBe(seasons.length * POSITIONS.length);
    expect(verdict.sentence).toContain(String(verdict.cells));
  });

  it("does not claim a win the numbers do not support", () => {
    const verdict = pooledVerdict(seasons);
    if (verdict.modelWins === verdict.seasons) {
      expect(verdict.sentence).not.toContain("ranks better than my projection");
    } else {
      expect(verdict.sentence).not.toContain(
        "I rank better than the last-five",
      );
    }
  });

  it("is what the mini-league verdict describes", () => {
    const leagues = seasons as unknown as LeagueSeason[];
    const beaten = leagues.filter(
      (season) =>
        (season.league.policies.advised?.mean ?? 0) >
        (season.league.policies.form_chaser?.mean ?? 0),
    ).length;

    const sentence = leagueVerdict(leagues);

    // The sentence that drifted said the form chaser won a season it did not.
    // Whichever way the artifact falls, the count has to come from the numbers.
    if (beaten === leagues.length) {
      expect(sentence).toContain(`all ${String(leagues.length)} seasons`);
      expect(sentence).not.toContain("beat me in");
    } else {
      expect(sentence).toContain(String(beaten));
    }
  });

  it("names a baseline that beat the projection, or does not mention one", () => {
    const leagues = seasons as unknown as LeagueSeason[];
    const crowdWins = leagues.filter(
      (season) =>
        (season.league.policies.crowd?.mean ?? 0) >
        (season.league.policies.advised?.mean ?? 0),
    );

    const sentence = leagueVerdict(leagues);

    if (crowdWins.length === 0) {
      expect(sentence).not.toContain("The crowd beat me");
    } else {
      for (const season of crowdWins) {
        expect(sentence).toContain(season.season);
      }
    }
  });
});

describe("verdicts on artifacts that do not exist yet", () => {
  const method = (
    label: string,
    spearman: number | null,
    byPosition: Record<string, number | null> = {},
  ) => ({
    label,
    spearman,
    meanAbsoluteError: null,
    topNHitRate: null,
    byPosition,
  });

  it("says the baseline wins when the baseline wins", () => {
    const verdict = pooledVerdict([
      {
        season: "2019-20",
        methods: [method("model", 0.3), method("recent_mean", 0.6)],
      },
    ]);
    expect(verdict.modelWins).toBe(0);
    expect(verdict.sentence).toContain("ranks better than my projection");
  });

  it("says so plainly when the seasons disagree", () => {
    const verdict = pooledVerdict([
      {
        season: "2019-20",
        methods: [method("model", 0.3), method("recent_mean", 0.6)],
      },
      {
        season: "2020-21",
        methods: [method("model", 0.6), method("recent_mean", 0.3)],
      },
    ]);
    expect(verdict.sentence).toContain("1 of 2 seasons");
  });

  it("refuses to compare a season that carries only one method", () => {
    const verdict = pooledVerdict([
      { season: "2019-20", methods: [method("model", 0.3)] },
    ]);
    expect(verdict.seasons).toBe(0);
    expect(verdict.sentence).toContain("nothing to compare");
  });

  it("counts only the position cells both methods measured", () => {
    const verdict = positionVerdict(
      [
        {
          season: "2019-20",
          methods: [
            method("model", 0.5, { GKP: 0.4, DEF: 0.5, MID: null, FWD: 0.2 }),
            method("recent_mean", 0.4, {
              GKP: 0.3,
              DEF: 0.6,
              MID: 0.4,
              FWD: 0.1,
            }),
          ],
        },
      ],
      POSITIONS,
    );
    expect(verdict.cells).toBe(3);
    expect(verdict.modelWins).toBe(2);
  });
});

describe("Overall Rank performance bands", () => {
  const band = (rankTo: number) => ({
    rankFrom: rankTo,
    rankTo,
    sampleSize: 20,
  });

  it.each([
    [1_000, "top 1k"],
    [10_000, "top 10k"],
    [50_000, "top 50k"],
    [100_000, "top 100k"],
    [250_000, "top 250k"],
    [500_000, "top 500k"],
    [500_001, "total flop"],
    [3_000_000, "total flop"],
  ])("labels rank %,i as %s", (rankTo, label) => {
    expect(rankPerformanceLabel(band(rankTo))).toBe(label);
  });

  it("uses the conservative edge of a measured range", () => {
    const range = { rankFrom: 100_000, rankTo: 600_000, sampleSize: 20 };
    expect(rankPerformanceLabel(range)).toBe("total flop");
    expect(rankBandClass(range)).toBe("is-flop");
  });

  it("does not invent a result without a sample", () => {
    expect(rankPerformanceLabel(null)).toBe("unrated");
    expect(rankBandClass(undefined)).toBe("is-unrated");
  });
});

describe("which captaincy theses the bootstrap separated", () => {
  const interval = (label: string, upper: number, better = false) => ({
    label,
    upper,
    better,
  });

  it("says nothing separated when nothing did", () => {
    // The important case, and the one a hand-written sentence would never
    // admit to: ten rules measured, no winner.
    expect(
      separableVerdict([interval("a", 0.7), interval("b", 0.3)]),
    ).toContain("Nothing here is separable");
  });

  it("names a rule that is measurably worse, not only one that is better", () => {
    const sentence = separableVerdict([
      interval("fine", 0.7),
      interval("bad", -0.1),
    ]);
    expect(sentence).toBe("Only bad loses to it.");
  });

  it("names both sides when both exist", () => {
    const sentence = separableVerdict([
      interval("good", 1.2, true),
      interval("fine", 0.7),
      interval("bad", -0.1),
      interval("worse", -0.4),
    ]);
    expect(sentence).toBe("Only good beats it, and bad and worse lose to it.");
  });

  it("says nothing at all when nothing was measured", () => {
    // An artifact predating the bootstrap. Silence, not a claim of a tie.
    expect(separableVerdict([])).toBe("");
  });

  it("describes the shipped artifact", () => {
    const shipped = (validation as { captainSignificance?: unknown[] })
      .captainSignificance as
      { label: string; upper: number; better: boolean }[] | undefined;
    if (shipped === undefined || shipped.length === 0) return;
    const sentence = separableVerdict(shipped);
    for (const entry of shipped) {
      const separated = entry.better || entry.upper < 0;
      expect(sentence.includes(entry.label)).toBe(separated);
    }
  });
});
