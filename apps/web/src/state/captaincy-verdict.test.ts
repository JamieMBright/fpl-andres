import { describe, expect, it } from "vitest";

import validation from "../data/validation.json";
import { captainEvidence } from "./captain-evidence";
import {
  SEASON_GAMEWEEKS,
  type CaptaincyInterval,
  captaincyVerdict,
  ceilingSentence,
  thesisTable,
  whichThesisVerdict,
} from "./captaincy-verdict";

/**
 * The Methodology page's captaincy paragraph used to be nine hand-copied
 * numbers. These tests exist because the claim it makes is not monotone in
 * those numbers: a rerun can flip "none of them" to "one of them", and a page
 * that keeps saying the first one is worse than a page with no verdict at all.
 */

function interval(
  label: string,
  improvement: number,
  lower: number,
  upper: number,
): CaptaincyInterval {
  return {
    label,
    weeks: 127,
    meanPoints: 6.9 + improvement,
    improvement,
    lower,
    upper,
    better: lower > 0,
  };
}

describe("the table the page reads", () => {
  const rows = [
    interval("form", -0.3, -0.5, -0.1),
    interval("template", 0.15, -0.34, 0.69),
    interval("crowd", 0.4, 0.1, 0.7),
  ];

  it("multiplies a per-week gap out to a season, which is the readable unit", () => {
    const [best] = thesisTable(rows);

    expect(best?.pointsPerSeason).toBeCloseTo(0.4 * SEASON_GAMEWEEKS, 6);
  });

  it("sorts by what the rule is worth, best first", () => {
    expect(thesisTable(rows).map((row) => row.label)).toEqual([
      "crowd",
      "template",
      "form",
    ]);
  });

  it("takes the verdict from the interval, never from the mean", () => {
    const table = thesisTable(rows);

    // Template is second on the mean and still unproven, because its interval
    // straddles zero. A table sorted on the average alone would crown it.
    expect(table.map((row) => row.verdict)).toEqual([
      "better",
      "unproven",
      "worse",
    ]);
  });

  it("gives every scored rule a plain-language description", () => {
    for (const row of thesisTable(validation.captainSignificance)) {
      expect(row.rule.length, row.label).toBeGreaterThan(0);
      expect(row.name, row.label).not.toBe(row.label);
    }
  });

  it("carries the interval through in the same unit as the headline", () => {
    const [best] = thesisTable(rows);

    expect(best?.lowPerSeason).toBeLessThan(best?.pointsPerSeason ?? 0);
    expect(best?.highPerSeason).toBeGreaterThan(best?.pointsPerSeason ?? 0);
  });
});

describe("captaincyVerdict", () => {
  it("takes the week count from the intervals", () => {
    expect(captaincyVerdict([interval("form", 0.1, -0.2, 0.4)]).weeks).toBe(
      127,
    );
  });

  it("ranks by improvement rather than trusting the artifact's order", () => {
    const verdict = captaincyVerdict([
      interval("form", -1.5, -2.5, -0.6),
      interval("template", 0.15, -0.34, 0.69),
    ]);
    expect(verdict.leader?.label).toBe("template");
  });

  it("separates the rules that clear zero from the rules that lose", () => {
    const verdict = captaincyVerdict([
      interval("template", 0.15, -0.34, 0.69),
      interval("upside", -1.2, -2.35, -0.13),
      interval("form", -1.57, -2.55, -0.68),
    ]);
    expect(verdict.better).toHaveLength(0);
    expect(verdict.worse.map((entry) => entry.label)).toEqual([
      "upside",
      "form",
    ]);
  });

  it("averages the reachable XI ceiling across seasons", () => {
    const verdict = captaincyVerdict(
      [interval("template", 0.15, -0.34, 0.69)],
      [
        {
          ownedCaptainPolicies: [
            { label: "expected_points", meanReachableCeiling: 14 },
          ],
        },
        {
          ownedCaptainPolicies: [
            { label: "expected_points", meanReachableCeiling: 16 },
          ],
        },
      ],
    );
    expect(verdict.ceilingPoints).toBe(15);
  });

  it("survives a season that scored no captaincy at all", () => {
    const verdict = captaincyVerdict(
      [interval("template", 0.15, -0.34, 0.69)],
      [
        { ownedCaptainPolicies: null },
        {
          ownedCaptainPolicies: [
            { label: "expected_points", meanReachableCeiling: 12 },
          ],
        },
      ],
    );
    expect(verdict.ceilingPoints).toBe(12);
  });
});

describe("whichThesisVerdict", () => {
  it("says none of them when nothing clears zero", () => {
    const which = whichThesisVerdict(
      captaincyVerdict([
        interval("template", 0.15, -0.34, 0.69),
        interval("form", -1.57, -2.55, -0.68),
      ]),
    );
    expect(which.headline).toBe("none of them");
    expect(which.detail).toContain("Not one interval clears zero");
    expect(which.detail).toContain("chasing form costs 1.57 a week");
  });

  it("names the winner when one appears", () => {
    // The whole point of deriving this: a rerun that finds an edge must not be
    // reported as "none of them".
    const which = whichThesisVerdict(
      captaincyVerdict([
        interval("template", 0.9, 0.4, 1.4),
        interval("form", -1.57, -2.55, -0.68),
      ]),
    );
    expect(which.headline).toBe("leaning toward the crowd");
    expect(which.detail).toContain(
      "only rule whose whole interval clears zero",
    );
    expect(which.detail).not.toContain("only findings here");
  });

  it("names every winner when several appear", () => {
    const which = whichThesisVerdict(
      captaincyVerdict([
        interval("template", 0.9, 0.4, 1.4),
        interval("crowd", 0.5, 0.1, 0.9),
      ]),
    );
    expect(which.headline).toBe(
      "leaning toward the crowd and captaining the most owned",
    );
  });

  it("drops the losing clause when nothing loses", () => {
    const which = whichThesisVerdict(
      captaincyVerdict([interval("template", 0.15, -0.34, 0.69)]),
    );
    expect(which.detail).not.toContain("measurably worse");
  });

  it("answers honestly when the artifact scored nothing", () => {
    const which = whichThesisVerdict(captaincyVerdict([]));
    expect(which.headline).toBe("nothing to answer with");
  });

  it("signs the interval bounds with a real minus sign", () => {
    const which = whichThesisVerdict(
      captaincyVerdict([interval("template", 0.15, -0.34, 0.69)]),
    );
    expect(which.detail).toContain("\u22120.34 to +0.69");
  });
});

describe("ceilingSentence", () => {
  it("states the gap between the best rule and the best available pick", () => {
    const sentence = ceilingSentence(
      captaincyVerdict(
        [
          interval("template", 0.15, -0.34, 0.69),
          interval("form", -1.57, -2.55, -0.68),
        ],
        [
          {
            ownedCaptainPolicies: [
              {
                label: "expected_points",
                meanReachableCeiling: 15.45,
              },
            ],
          },
        ],
      ),
    );
    expect(sentence).toContain("15.45 points");
    // 0.15 - (-1.57) = 1.72, rounded up to a tenth.
    expect(sentence).toContain("under 1.8 points a week");
    expect(sentence).toContain("more than 8 sit untouched");
  });

  it("says nothing when there is no ceiling to compare against", () => {
    expect(
      ceilingSentence(
        captaincyVerdict([interval("template", 0.15, -0.34, 0.69)]),
      ),
    ).toBe("");
  });
});

describe("the shipped artifact", () => {
  it("renders only evidence explicitly scoped to model-owned XIs", () => {
    const evidence = captainEvidence(validation);
    const verdict = captaincyVerdict(evidence.significance, evidence.seasons);
    const which = whichThesisVerdict(verdict);

    if (evidence.seasons.length === 0) {
      expect(verdict.weeks).toBe(0);
      expect(which.headline).toBe("nothing to answer with");
      expect(ceilingSentence(verdict)).toBe("");
    } else {
      expect(verdict.weeks).toBeGreaterThan(0);
      expect(which.headline).not.toBe("nothing to answer with");
      expect(ceilingSentence(verdict)).not.toBe("");
    }
  });

  it("agrees with its own interval bounds", () => {
    // A rule reported as better must actually have a lower bound above zero.
    const evidence = captainEvidence(validation);
    const verdict = captaincyVerdict(evidence.significance, evidence.seasons);
    for (const entry of verdict.better) {
      expect(entry.lower).toBeGreaterThan(0);
    }
    for (const entry of verdict.worse) {
      expect(entry.upper).toBeLessThan(0);
    }
  });
});
