/**
 * The captaincy verdict, computed from the artifact rather than typed out.
 *
 * The Methodology page asserted "measured over 127 paired
 * gameweeks: none of them", quoted +0.15 with an interval of -0.34 to +0.69,
 * named the two losing rules and their costs, and put the shortlist ceiling at
 * 15.45 against a best thesis of 7.12. Eight numbers and three claims, all
 * hand-copied out of one backtest run.
 *
 * Every one of them moves when the model changes, and the model changes on a
 * schedule now. Worse, the claims are not monotone in the numbers: fixing one
 * arithmetic error in this repository inverted the entire captaincy ordering,
 * which would have left the page confidently reporting the opposite of its own
 * chart. Prose that contradicts the table beneath it is worse than no prose.
 *
 * So the page asks these functions and the functions read `validation.json`.
 * A rerun that finds a winner writes a page that reports a winner.
 *
 * Everything returned here is plain text. Emphasis is the caller's job, which
 * is why the headline clause comes back separately instead of as markup inside
 * a string: a derived sentence is not a reason to reach for innerHTML.
 */

import { oneDecimal, twoDecimals } from "../format";

export interface CaptaincyInterval {
  label: string;
  weeks: number;
  meanPoints: number;
  improvement: number;
  lower: number;
  upper: number;
  better: boolean;
}

export interface CaptaincySeason {
  captaincy?: { label: string; meanBestPoints: number | null }[] | null;
}

export interface CaptaincyVerdict {
  /** Paired gameweeks behind every interval, or 0 when the artifact is empty. */
  weeks: number;
  /** Theses whose whole interval sits above zero. */
  better: CaptaincyInterval[];
  /** Theses whose whole interval sits below zero. */
  worse: CaptaincyInterval[];
  /** The thesis at the top of the table, whether or not it is separable. */
  leader: CaptaincyInterval | null;
  /** Best mean of any thesis, against the best pick the shortlist offered. */
  bestThesisPoints: number | null;
  ceilingPoints: number | null;
}

/** Two halves of one sentence, so the caller can emphasise the verdict itself. */
export interface Verdict {
  lead: string;
  headline: string;
  detail: string;
}

/** Names as the page writes them: the artifact's labels are snake_case keys. */
const THESIS_NAMES: Record<string, string> = {
  availability_adjusted: "adjusting for the chance he starts",
  ceiling_and_fixture: "captaining the biggest ceiling against its fixture",
  components: "captaining the best component reconstruction",
  crowd: "captaining the most owned",
  differential: "captaining away from the crowd",
  form: "chasing form",
  robust: "captaining the safest",
  set_and_forget: "picking one captain in August and never changing",
  template: "leaning toward the crowd",
  upside: "captaining the biggest upside",
};

export function thesisName(label: string): string {
  return THESIS_NAMES[label] ?? label;
}

/** One line each, in the words the rule would use if it could speak. */
const THESIS_RULES: Record<string, string> = {
  expected_points: "Captain the highest projected scorer.",
  availability_adjusted:
    "The same, after multiplying each projection by his chance of starting.",
  ceiling_and_fixture:
    "Captain the biggest best-case afternoon, scaled by how kind the fixture is.",
  components:
    "Captain the highest score rebuilt from its parts rather than from the total.",
  crowd: "Captain whoever the most managers own.",
  differential: "Captain the best projection nobody else owns.",
  form: "Captain whoever has scored most lately, ignoring anyone under 2.0.",
  robust: "Captain the safest: the projection minus its own spread.",
  set_and_forget:
    "Pick the most owned player in the first week and never change.",
  template:
    "Captain the best projection, nudged toward whoever is widely owned.",
  upside: "Captain the biggest upside: the projection plus its own spread.",
};

export interface ThesisRow {
  label: string;
  name: string;
  rule: string;
  /** What a whole season of this rule is worth against the projection. */
  pointsPerSeason: number;
  /** The same, as the interval it was measured on. */
  lowPerSeason: number;
  highPerSeason: number;
  verdict: "better" | "worse" | "unproven";
}

/** Gameweeks in a season, so a per-week gap can be read as a season's worth. */
export const SEASON_GAMEWEEKS = 38;

/**
 * The whole comparison as one table, sorted by what it is worth.
 *
 * A gap of a tenth of a point a week is unreadable and a season's worth of it
 * is not, so the per-week figures are multiplied out. Nothing else changes: the
 * verdict still comes from the interval, so a rule worth points on average and
 * unproven on the interval says so in its own row.
 */
export function thesisTable(
  intervals: readonly CaptaincyInterval[],
): ThesisRow[] {
  return [...intervals]
    .sort((left, right) => right.improvement - left.improvement)
    .map((entry) => ({
      label: entry.label,
      name: thesisName(entry.label),
      rule: THESIS_RULES[entry.label] ?? "",
      pointsPerSeason: entry.improvement * SEASON_GAMEWEEKS,
      lowPerSeason: entry.lower * SEASON_GAMEWEEKS,
      highPerSeason: entry.upper * SEASON_GAMEWEEKS,
      verdict: entry.better ? "better" : entry.upper < 0 ? "worse" : "unproven",
    }));
}

export function captaincyVerdict(
  intervals: readonly CaptaincyInterval[],
  seasons: readonly CaptaincySeason[] = [],
): CaptaincyVerdict {
  const ceilings = seasons
    .flatMap((season) => season.captaincy ?? [])
    .map((entry) => entry.meanBestPoints)
    .filter((value): value is number => value !== null);

  // The artifact ships the table already sorted, but a verdict that depends on
  // upstream sort order is a verdict waiting to be broken by a refactor.
  const ranked = [...intervals].sort((a, b) => b.improvement - a.improvement);

  return {
    weeks: ranked[0]?.weeks ?? 0,
    better: ranked.filter((entry) => entry.better),
    worse: ranked.filter((entry) => entry.upper < 0),
    leader: ranked[0] ?? null,
    bestThesisPoints: ranked.length
      ? Math.max(...ranked.map((entry) => entry.meanPoints))
      : null,
    ceilingPoints: ceilings.length
      ? ceilings.reduce((total, value) => total + value, 0) / ceilings.length
      : null,
  };
}

/** "So which one should you use?" — answered from the intervals. */
export function whichThesisVerdict(verdict: CaptaincyVerdict): Verdict {
  const leader = verdict.leader;
  if (verdict.weeks === 0 || leader === null) {
    return {
      lead: "No backtest in this artifact scored a captaincy thesis, so there is ",
      headline: "nothing to answer with",
      detail: ".",
    };
  }

  const lead = `Measured over ${String(verdict.weeks)} paired gameweeks: `;
  const band = `${signed(leader.lower)} to ${signed(leader.upper)}`;

  if (verdict.better.length === 0) {
    return {
      lead,
      headline: "none of them",
      detail:
        ". Not one interval clears zero. The rule that tops the table beats the " +
        `projection by ${twoDecimals.format(leader.improvement)} points a week with an ` +
        `interval running from ${band}, so the table\u2019s own ordering sits inside ` +
        `its own noise.${worseClause(verdict)}`,
    };
  }

  const winners = nameList(
    verdict.better.map((entry) => thesisName(entry.label)),
  );
  const preamble =
    verdict.better.length === 1
      ? "It is the only rule whose whole interval clears zero"
      : "Those are the rules whose whole intervals clear zero";
  return {
    lead,
    headline: winners,
    detail:
      `. ${preamble}, and the best of them beats the projection by ` +
      `${twoDecimals.format(leader.improvement)} points a week on an interval from ` +
      `${band}.${worseClause(verdict)}`,
  };
}

function worseClause(verdict: CaptaincyVerdict): string {
  if (verdict.worse.length === 0) return "";
  const costs = nameList(
    verdict.worse.map(
      (entry) =>
        `${thesisName(entry.label)} costs ${twoDecimals.format(Math.abs(entry.improvement))} a week`,
    ),
  );
  const only =
    verdict.worse.length === 1
      ? " That is the only finding here, and it is negative."
      : " Those are the only findings here, and they are all negative.";
  const framing = verdict.better.length === 0 ? only : "";
  const subject =
    verdict.worse.length === 1
      ? "One rule is measurably worse"
      : `${cardinal(verdict.worse.length)} rules are measurably worse`;
  const interval =
    verdict.worse.length === 1 ? "with an interval" : "all with intervals";
  return ` ${subject} \u2014 ${costs}, ${interval} entirely below zero.${framing}`;
}

/** The gap between the best rule and the best pick the shortlist offered. */
export function ceilingSentence(verdict: CaptaincyVerdict): string {
  const { ceilingPoints, bestThesisPoints, leader } = verdict;
  if (ceilingPoints === null || bestThesisPoints === null || leader === null) {
    return "";
  }
  const untouched = ceilingPoints - bestThesisPoints;
  const worst = verdict.worse.at(-1) ?? leader;
  const argument =
    Math.ceil((leader.improvement - worst.improvement) * 10) / 10;
  return (
    "The best captain available on the shortlist averages " +
    `${twoDecimals.format(ceilingPoints)} points and the best thesis takes ` +
    `${twoDecimals.format(bestThesisPoints)}, so the whole argument between them is ` +
    `worth under ${oneDecimal.format(argument)} points a week while more than ` +
    `${String(Math.floor(untouched))} sit untouched. The gap that matters is not ` +
    "between the rules."
  );
}

function signed(value: number): string {
  const sign = value < 0 ? "\u2212" : "+";
  return `${sign}${twoDecimals.format(Math.abs(value))}`;
}

function nameList(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1] ?? ""}`;
}

function cardinal(count: number): string {
  const words = ["Zero", "One", "Two", "Three", "Four", "Five", "Six"];
  return words[count] ?? String(count);
}
