import type { ChipCall, PlanGameweek, PlanPlayer } from "./season-plan";
import { CONFIDENCE_NOTE, pairTransfers } from "./season-plan";
import validation from "../data/validation.json";
import seasonInputs from "../data/season-inputs.json";
import { captainEvidence } from "./captain-evidence";
import { captaincyVerdict } from "./captaincy-verdict";
import { MARKET_EXPECTATION_HOURS } from "./market-health";
import { nextDeadlineAt } from "./season-deadlines";

/**
 * Why the plan did what it did, in words, derived from the plan itself.
 *
 * Everything here is read off the published artifact rather than invented in
 * the browser. A card that says "trust me" is not evidence; a card that says
 * which fixture, which price and how many points is.
 */

/**
 * What the backtest actually found about armbands, in one clause.
 *
 * Nine rules were scored against captaining the highest projected scorer and
 * the page has to report whichever way that came out, because the ordering has
 * already inverted once on a single arithmetic fix.
 */
export const CAPTAINCY_VERDICT = (() => {
  const evidence = captainEvidence(validation);
  const verdict = captaincyVerdict(evidence.significance);
  if (verdict.weeks === 0) return "no thesis has been scored against it yet.";
  const beaten = verdict.better.length;
  return beaten === 0
    ? `none of ${String(evidence.significance.length)} published theses beat it over ${String(verdict.weeks)} paired gameweeks.`
    : `${String(beaten)} of ${String(evidence.significance.length)} published theses did beat it over ${String(verdict.weeks)} paired gameweeks, so this rule is now the weaker one.`;
})();

/**
 * What counts as paying for a starter, by position. A benched player above the
 * line is money doing nothing, and the card says so rather than leaving the
 * reader to notice.
 */
export const PREMIUM_TENTHS: Readonly<Record<string, number>> = {
  GKP: 50,
  DEF: 55,
  MID: 75,
  FWD: 75,
};

const DIFFICULTY_WORD: Readonly<Record<number, string>> = {
  1: "very soft",
  2: "soft",
  3: "even",
  4: "hard",
  5: "very hard",
};

function money(tenths: number): string {
  return `£${(tenths / 10).toFixed(1)}m`;
}

function points(value: number): string {
  return value.toFixed(1);
}

/** The player's own expected score this week, before the armband. */
function scoreOf(week: PlanGameweek, player: PlanPlayer): number {
  return week.expected[String(player.code)] ?? 0;
}

function captainRoutes(player: PlanPlayer): string {
  const row = seasonInputs.players.find(
    (candidate) => candidate.code === player.code,
  ) as { routes?: Record<string, number> } | undefined;
  if (!row?.routes) return "route breakdown unavailable";
  const labels: Record<string, string> = {
    appearance: "appearance",
    attacking: "attacking",
    cleanSheet: "clean sheet",
    bonus: "bonus",
    defensiveContribution: "DefCon",
  };
  const routes = Object.entries(row.routes)
    .filter(
      ([key, value]) => labels[key] !== undefined && Math.abs(value) >= 0.05,
    )
    .sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]))
    .slice(0, 3)
    .map(
      ([key, value]) =>
        `${labels[key]} ${value >= 0 ? "+" : ""}${value.toFixed(1)}`,
    );
  return routes.length > 0
    ? routes.join(", ")
    : "no published route contribution";
}

export function captainLine(week: PlanGameweek): string {
  const captainScore = scoreOf(week, week.captain);
  const viceScore = scoreOf(week, week.viceCaptain);
  const gap = captainScore - viceScore;
  const fixture = (week.opponents[week.captain.club] ?? []).join(", ");
  const contest = Math.abs(gap) < 1 ? " This is a contested call." : "";
  return `${week.captain.name} leads ${week.viceCaptain.name} ${points(Math.abs(gap))} points on expected score${fixture ? `, with ${fixture}` : ""}. Main routes: ${captainRoutes(week.captain)}.${contest}`;
}

export function isPremium(player: PlanPlayer): boolean {
  const line = PREMIUM_TENTHS[player.position];
  return line !== undefined && player.priceTenths > line;
}

/**
 * Why this transfer, naming both players and what separates them.
 *
 * One line per swap. Run together as a paragraph, a double transfer read as a
 * single sentence about four players and there was no way to tell which price
 * and which fixture belonged to which move.
 */
export function moveLines(week: PlanGameweek): string[] {
  if (week.chip) {
    const changes = week.transfersIn.length;
    const revert = week.revertsAfter
      ? " The squad goes back to what it was for the following week."
      : " The squad is kept from here on.";
    return [
      `${week.chip}: ${changes} ${changes === 1 ? "change" : "changes"}, ` +
        `no transfer charged and no free transfer spent.${revert}`,
    ];
  }

  if (week.transfersIn.length === 0) {
    return [week.event === 1 ? "Opening squad." : "Roll the free transfer."];
  }

  const swaps = pairTransfers(week.transfersOut, week.transfersIn).map(
    ({ out: outgoing, in: incoming }) => {
      const gain = scoreOf(week, incoming) - scoreOf(week, outgoing);
      const spend = incoming.priceTenths - outgoing.priceTenths;
      const fixture = (week.opponents[incoming.club] ?? []).join(", ");

      const parts = [`${outgoing.name} out, ${incoming.name} in`];
      parts.push(
        gain >= 0
          ? `+${points(gain)} this week`
          : `${points(gain)} now, for later`,
      );
      if (fixture) parts.push(`faces ${fixture}`);
      if (spend > 0) parts.push(`${money(spend)} of the bank`);
      if (spend < 0) parts.push(`frees ${money(-spend)}`);
      return `${parts.join("; ")}.`;
    },
  );

  if (week.transferCostPoints > 0) {
    swaps.push(
      `\u2212${String(week.transferCostPoints)} for the extra transfers, already in the total.`,
    );
  }
  return swaps;
}

/** The money, one fact per line, because a paragraph of figures reads as none. */
export function moneyLines(week: PlanGameweek): string[] {
  const spend = (players: readonly PlanPlayer[]) =>
    players.reduce((total, player) => total + player.priceTenths, 0);
  const eleven = spend(week.starters);
  const bench = spend(week.bench);

  const lines = [
    `${money(eleven + bench)} squad, of which ${money(eleven)} is playing.`,
    `${money(bench)} on the bench.`,
    `${money(week.bankAfterTenths)} in the bank.`,
  ];

  const parked = week.bench.filter(isPremium);
  for (const player of parked) {
    lines.push(
      `${money(player.priceTenths)} benched: ${player.name} (${player.position}).`,
    );
  }
  return lines;
}

/**
 * The fixtures, rated, with the hard ones named.
 *
 * Returns null where no club in the squad has a rating, which happens when
 * every one of them is newly promoted and has no measured record of its own. A
 * promoted *opponent* is rated: the tie is being played, so it is assumed soft
 * until that club's own results arrive.
 */
export function fixtureReason(week: PlanGameweek): string | null {
  const rated = week.starters
    .map((player) => ({
      player,
      rating: week.difficulty[player.club] ?? null,
    }))
    .filter(
      (entry): entry is { player: PlanPlayer; rating: number } =>
        entry.rating !== null,
    );
  if (rated.length === 0) return null;

  const mean =
    rated.reduce((total, entry) => total + entry.rating, 0) / rated.length;
  const hardest = rated.filter((entry) => entry.rating >= 4);
  const blanks = week.starters.filter(
    (player) => (week.opponents[player.club] ?? []).length === 0,
  );

  const parts = [
    `Fixtures ${mean.toFixed(1)}/5, ${DIFFICULTY_WORD[Math.round(mean)] ?? "even"}.`,
  ];

  if (hardest.length > 0) {
    // Naming who has the hard tie is the point: an average hides it.
    const named = hardest
      .map(
        (entry) =>
          `${entry.player.name} at ${(week.opponents[entry.player.club] ?? []).join(", ")}`,
      )
      .slice(0, 3)
      .join(", ");
    parts.push(`Rated four or worse: ${named}.`);
  }
  if (blanks.length > 0) {
    parts.push(
      `No fixture: ${blanks.map((player) => player.name).join(", ")}.`,
    );
  }
  return parts.join(" ");
}

/**
 * A deadline is its own kind of uncertainty. The confidence band says how far
 * a gameweek is from the calibrated horizon; this says whether the next
 * deadline is still far enough away for lineup and market evidence to move.
 */
export function deadlineAdvice(
  week: PlanGameweek,
  now: Date = new Date(),
): string | null {
  const next = nextDeadlineAt(now);
  if (!next || next.event !== week.event) return null;
  const hoursUntil = (Date.parse(next.deadline) - now.getTime()) / 3_600_000;
  if (hoursUntil <= MARKET_EXPECTATION_HOURS) return null;
  return `The deadline is more than ${String(MARKET_EXPECTATION_HOURS)} hours away. If you do not need to act now, wait until closer to the deadline: team news and market evidence can still change this call.`;
}

/** What the week actually rests on, rather than a repeat of the band name. */
export function confidenceReason(week: PlanGameweek): string {
  const eleven = week.starters.map((player) => scoreOf(week, player));
  const total = eleven.reduce((a, b) => a + b, 0);
  const captain = scoreOf(week, week.captain);
  const parts: string[] = [];

  if (total > 0) {
    const share = (captain * 2) / (total + captain);
    const runnerUp = week.starters
      .filter((player) => player.code !== week.captain.code)
      .map((player) => ({ player, score: scoreOf(week, player) }))
      .sort((left, right) => right.score - left.score)[0];
    parts.push(
      `${week.captain.name} (C) is ${Math.round(share * 100)}% of the haul.`,
    );
    if (runnerUp) {
      // Naming the runner-up is what makes the armband arguable rather than
      // asserted, and it is usually a defender because the 2025/26 defensive
      // contribution route pays them for work that never used to score.
      parts.push(
        `Picked over ${runnerUp.player.name} by ${points(captain - runnerUp.score)}.`,
      );
    }
  }

  const thin = week.starters.filter((player) => scoreOf(week, player) < 2);
  if (thin.length > 0) {
    parts.push(
      `Under two points: ${thin.map((player) => player.name).join(", ")}.`,
    );
  }

  parts.push(...benchedPremiumReasons(week));

  const rated = week.starters
    .map((player) => week.difficulty[player.club] ?? null)
    .filter((rating): rating is number => rating !== null);
  if (rated.length > 0) {
    const hard = rated.filter((rating) => rating >= 4).length;
    const soft = rated.filter((rating) => rating <= 2).length;
    parts.push(`${String(soft)} soft ties, ${String(hard)} hard.`);
  }

  parts.push(CONFIDENCE_NOTE[week.confidence]);
  return parts.join(" ");
}

/**
 * A premium on the bench has to be argued for in numbers, not just noticed.
 *
 * The money section already says a benched premium is a lot to leave out. That
 * is the observation, not the reasoning, and the two were in different sections
 * so the card raised the objection and never answered it. Price is the gate:
 * above the line for his position, the card owes the reader the score that
 * displaced him and the size of the gap.
 */
export function benchedPremiumReasons(week: PlanGameweek): string[] {
  return week.bench.filter(isPremium).map((player) => {
    const benched = scoreOf(week, player);
    const fixture = (week.opponents[player.club] ?? []).join(", ");
    const blank = (week.opponents[player.club] ?? []).length === 0;
    const picked = week.starters
      .filter((starter) => starter.position === player.position)
      .map((starter) => ({ starter, score: scoreOf(week, starter) }))
      .sort((left, right) => left.score - right.score)[0];

    const opening = `${player.name} benched on ${points(benched)}`;

    if (blank) {
      return `${opening}: no fixture.`;
    }
    if (!picked) {
      return `${opening}: no ${player.position} started ahead of him, so it is a squad rule and not a call on him.`;
    }
    const gap = picked.score - benched;
    if (gap <= 0) {
      // Started anyway: the eleven is a formation, not a ranking.
      return `${opening}, ${points(-gap)} above ${picked.starter.name}. Out on formation, not projection.`;
    }
    return `${opening} against ${picked.starter.name} on ${points(picked.score)}, a gap of ${points(gap)}${fixture ? `, facing ${fixture}` : ""}.`;
  });
}

/**
 * The chip line, or an honest statement that none is due.
 *
 * `played` is whether the squad below was solved with the chip in hand. On a
 * published plan it was; on a manager's own solve the chip is a recommendation
 * sitting beside an ordinary week, and a badge that did not say so read as a
 * Wildcard being spent on the single transfer printed under it.
 */
export function chipReason(chip: ChipCall | null, played = true): string {
  if (!chip) return "None this week.";
  const caveat = played
    ? ""
    : " Advice for this week, not something the squad below has been rebuilt around: play it in FPL and the transfers are free.";
  return `${chip.chip} \u2014 ${chip.note}.${caveat}`;
}
