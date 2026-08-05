import { describe, expect, it } from "vitest";

import validation from "../data/validation.json";
import {
  pooledVerdict,
  positionVerdict,
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
