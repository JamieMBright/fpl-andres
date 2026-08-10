import seasonInputs from "../data/season-inputs.json";

/**
 * How much of a bookmaker's view actually reached the published projection.
 *
 * The method page described the market's contribution in the present tense for
 * months while the ingestion had never once produced a file, so every blend was
 * a no-op and nothing on the site could say so. A page that claims a source it
 * is not reading is worse than a page with no claim: it is the same failure as
 * a hand-written verdict drifting from the table under it, and this repository
 * has been caught by that twice.
 *
 * So the artifact carries the counts and the page reads them. A run that starts
 * blending writes a page that says it is blending.
 */

export interface MarketReach {
  attackingRoutes: number;
  playersQuoted: number;
  cardRoutes: number;
  playersQuotedForCards: number;
  startRatesCut: number;
  squadsNamed: number;
  fixtureRungs: number;
}

const NOTHING: MarketReach = {
  attackingRoutes: 0,
  playersQuoted: 0,
  cardRoutes: 0,
  playersQuotedForCards: 0,
  startRatesCut: 0,
  squadsNamed: 0,
  fixtureRungs: 0,
};

/** Absent from artifacts published before the counts were carried. */
export function marketReach(): MarketReach {
  const carried = (seasonInputs as { market?: Partial<MarketReach> }).market;
  return carried ? { ...NOTHING, ...carried } : NOTHING;
}

/** True where no bookmaker moved a single number in the shipped projection. */
export function marketIsSilent(reach: MarketReach = marketReach()): boolean {
  return (
    reach.attackingRoutes === 0 &&
    reach.cardRoutes === 0 &&
    reach.startRatesCut === 0 &&
    reach.fixtureRungs === 0
  );
}

/** What the shipped projection owes to a bookmaker, in one sentence. */
export function marketSentence(reach: MarketReach = marketReach()): string {
  if (marketIsSilent(reach)) {
    return (
      "None of it is switched on yet. No bookmaker feed has reached a " +
      "published run, so every number on this site comes from the record " +
      "alone and everything below describes what happens when the odds arrive."
    );
  }
  const parts: string[] = [];
  if (reach.attackingRoutes > 0) {
    parts.push(
      `${String(reach.attackingRoutes)} attacking routes from ${String(reach.playersQuoted)} players quoted`,
    );
  }
  if (reach.cardRoutes > 0) {
    parts.push(`${String(reach.cardRoutes)} card routes`);
  }
  if (reach.startRatesCut > 0) {
    parts.push(
      `${String(reach.startRatesCut)} start rates cut across ${String(reach.squadsNamed)} named squads`,
    );
  }
  if (reach.fixtureRungs > 0) {
    parts.push(`${String(reach.fixtureRungs)} fixture rungs`);
  }
  const list =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1] ?? ""}`;
  return `In the run this page is built from, a bookmaker moved ${list}.`;
}
