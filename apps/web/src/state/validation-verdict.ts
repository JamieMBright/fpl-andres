/**
 * The calibration verdicts, derived from the artifact instead of typed out.
 *
 * The page used to state in prose that the naive last-five average "ranks
 * better than my projection in every season I tested". That was true when it
 * was written and stopped being true when the model started pricing the
 * fixture and the defensive-contribution route: the shipped artifact has the
 * model ahead on rank correlation, error and hit rate in all four seasons.
 *
 * Nobody noticed, because a sentence in JSX is not checked against the numbers
 * beside it. So the sentence is computed now. A future run that reverses the
 * result reverses the copy, and the test below this file's export fails if the
 * two ever disagree.
 */

export interface VerdictMethod {
  label: string;
  spearman: number | null;
  meanAbsoluteError: number | null;
  topNHitRate: number | null;
  byPosition: Record<string, number | null>;
}

export interface VerdictSeason {
  season: string;
  methods: VerdictMethod[];
}

export interface PooledVerdict {
  /** Seasons where the model's pooled rank correlation beats the baseline's. */
  modelWins: number;
  seasons: number;
  sentence: string;
}

export interface PositionVerdict {
  cells: number;
  modelWins: number;
  sentence: string;
}

function methodOf(
  season: VerdictSeason,
  label: string,
): VerdictMethod | undefined {
  return season.methods.find((method) => method.label === label);
}

/** How the model and the last-five average compare when every player is pooled. */
export function pooledVerdict(
  seasons: readonly VerdictSeason[],
): PooledVerdict {
  const comparable = seasons.filter((season) => {
    const mine = methodOf(season, "model")?.spearman;
    const naive = methodOf(season, "recent_mean")?.spearman;
    return (
      mine !== null &&
      mine !== undefined &&
      naive !== null &&
      naive !== undefined
    );
  });
  const modelWins = comparable.filter((season) => {
    const mine = methodOf(season, "model")?.spearman ?? 0;
    const naive = methodOf(season, "recent_mean")?.spearman ?? 0;
    return mine > naive;
  }).length;

  const total = comparable.length;
  if (total === 0) {
    return {
      modelWins: 0,
      seasons: 0,
      sentence:
        "No season in this artifact carries both a projection and a baseline, so there is nothing to compare.",
    };
  }
  if (modelWins === total) {
    return {
      modelWins,
      seasons: total,
      sentence:
        `I rank better than the last-five average in all ${String(total)} seasons. ` +
        "That is a weaker claim than it looks: this test has no squad, no budget " +
        "and no transfers, and pooling every position together mostly measures " +
        "whether a keeper can be told from a forward. The next section is the one " +
        "that decides anything.",
    };
  }
  if (modelWins === 0) {
    return {
      modelWins,
      seasons: total,
      sentence:
        "The dumbest possible baseline \u2014 a player's last five scores, averaged \u2014 " +
        `ranks better than my projection in all ${String(total)} seasons I tested. ` +
        "I am not going to hide that. But read the next section before drawing a " +
        "conclusion from it.",
    };
  }
  return {
    modelWins,
    seasons: total,
    sentence:
      `I rank better than the last-five average in ${String(modelWins)} of ${String(total)} seasons ` +
      "and worse in the rest. Pooled across every position this test is dominated " +
      "by cross-position calibration, which nobody trades on. The next section is " +
      "the one that decides anything.",
  };
}

/** How the two compare inside each position, which is where a squad is picked. */
export function positionVerdict(
  seasons: readonly VerdictSeason[],
  positions: readonly string[],
): PositionVerdict {
  let cells = 0;
  let modelWins = 0;
  for (const season of seasons) {
    for (const position of positions) {
      const mine = methodOf(season, "model")?.byPosition[position];
      const naive = methodOf(season, "recent_mean")?.byPosition[position];
      if (mine === null || mine === undefined) continue;
      if (naive === null || naive === undefined) continue;
      cells += 1;
      if (mine > naive) modelWins += 1;
    }
  }

  if (cells === 0) {
    return {
      cells,
      modelWins,
      sentence:
        "No position in this artifact carries both a projection and a baseline.",
    };
  }
  const clause =
    modelWins === cells
      ? `I beat the baseline in every position, in every season \u2014 ${String(cells)} out of ${String(cells)} cells.`
      : `I beat the baseline in ${String(modelWins)} of ${String(cells)} season-position cells.`;
  return {
    cells,
    modelWins,
    sentence:
      `${clause} Within a position is the comparison that matters, because you ` +
      "never choose a keeper against a forward. It is still a ranking test with " +
      "no budget in it.",
  };
}

export interface SeparableInterval {
  label: string;
  upper: number;
  /** True only when the whole interval sits above zero. */
  better: boolean;
}

/**
 * Which captaincy theses the bootstrap could separate from the projection.
 *
 * Counted rather than written down, for the same reason as everything else in
 * this file: a sentence naming which rules won is exactly the sentence that
 * goes stale the next time CI reruns the backtest.
 */
export function separableVerdict(
  verdicts: readonly SeparableInterval[],
): string {
  if (verdicts.length === 0) return "";
  const better = verdicts.filter((entry) => entry.better);
  const worse = verdicts.filter((entry) => !entry.better && entry.upper < 0);
  if (better.length === 0 && worse.length === 0) {
    return "Nothing here is separable from the projection.";
  }
  const clauses: string[] = [];
  if (better.length > 0) clauses.push(`${nameList(better)} beat it`);
  if (worse.length > 0) clauses.push(`${nameList(worse)} lose to it`);
  return `Only ${clauses.join(", and ")}.`;
}

function nameList(entries: readonly SeparableInterval[]): string {
  const names = entries.map((entry) => entry.label);
  if (names.length === 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1] ?? ""}`;
}
