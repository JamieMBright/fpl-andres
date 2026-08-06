import { describe, expect, it } from "vitest";

import validation from "../data/validation.json";
import {
  type CaptaincyInterval,
  captaincyVerdict,
  ceilingSentence,
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

  it("averages the shortlist ceiling across seasons", () => {
    const verdict = captaincyVerdict(
      [interval("template", 0.15, -0.34, 0.69)],
      [
        { captaincy: [{ label: "model", meanBestPoints: 14 }] },
        { captaincy: [{ label: "model", meanBestPoints: 16 }] },
      ],
    );
    expect(verdict.ceilingPoints).toBe(15);
  });

  it("survives a season that scored no captaincy at all", () => {
    const verdict = captaincyVerdict(
      [interval("template", 0.15, -0.34, 0.69)],
      [
        { captaincy: null },
        { captaincy: [{ label: "model", meanBestPoints: 12 }] },
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
        [{ captaincy: [{ label: "model", meanBestPoints: 15.45 }] }],
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
  it("produces a verdict the page can render", () => {
    const verdict = captaincyVerdict(
      validation.captainSignificance,
      validation.seasons,
    );
    const which = whichThesisVerdict(verdict);

    expect(verdict.weeks).toBeGreaterThan(0);
    expect(which.headline).not.toBe("nothing to answer with");
    expect(ceilingSentence(verdict)).not.toBe("");
  });

  it("agrees with its own interval bounds", () => {
    // A rule reported as better must actually have a lower bound above zero.
    const verdict = captaincyVerdict(
      validation.captainSignificance,
      validation.seasons,
    );
    for (const entry of verdict.better) {
      expect(entry.lower).toBeGreaterThan(0);
    }
    for (const entry of verdict.worse) {
      expect(entry.upper).toBeLessThan(0);
    }
  });
});
