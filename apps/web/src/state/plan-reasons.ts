import type { ChipCall, PlanGameweek, PlanPlayer } from "./season-plan";
import { CONFIDENCE_NOTE } from "./season-plan";
import validation from "../data/validation.json";
import { captaincyVerdict } from "./captaincy-verdict";

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
const CAPTAINCY_VERDICT = (() => {
  const verdict = captaincyVerdict(validation.captainSignificance);
  if (verdict.weeks === 0) return "no thesis has been scored against it yet.";
  const beaten = verdict.better.length;
  return beaten === 0
    ? `none of ${String(validation.captainSignificance.length)} published theses beat it over ${String(verdict.weeks)} paired gameweeks.`
    : `${String(beaten)} of ${String(validation.captainSignificance.length)} published theses did beat it over ${String(verdict.weeks)} paired gameweeks, so this rule is now the weaker one.`;
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

export function isPremium(player: PlanPlayer): boolean {
  const line = PREMIUM_TENTHS[player.position];
  return line !== undefined && player.priceTenths > line;
}

/**
 * Why this transfer, naming both players and what separates them.
 *
 * The old text said "inside the free transfer, so it costs nothing", which
 * explains the accounting and not the decision.
 */
export function moveReason(week: PlanGameweek): string {
  if (week.chip) {
    const changes = week.transfersIn.length;
    const revert = week.revertsAfter
      ? " The squad goes back to what it was for the following week."
      : " The squad is kept from here on.";
    return (
      `${week.chip}: ${changes} ${changes === 1 ? "change" : "changes"}, ` +
      `no transfer charged and no free transfer spent.${revert}`
    );
  }

  if (week.transfersIn.length === 0) {
    return week.event === 1
      ? "Opening squad."
      : "Nothing gains more than simply holding, so roll the free transfer.";
  }

  const swaps = week.transfersIn.map((incoming, index) => {
    const outgoing = week.transfersOut[index];
    const gain = outgoing
      ? scoreOf(week, incoming) - scoreOf(week, outgoing)
      : scoreOf(week, incoming);
    const spend = outgoing ? incoming.priceTenths - outgoing.priceTenths : 0;
    const fixture = (week.opponents[incoming.club] ?? []).join(", ");

    const parts = [
      outgoing
        ? `${outgoing.name} out, ${incoming.name} in`
        : `${incoming.name} in`,
    ];
    parts.push(
      gain >= 0
        ? `worth ${points(gain)} more this week`
        : `worth ${points(-gain)} less this week, taken for what follows`,
    );
    if (fixture) parts.push(`he faces ${fixture}`);
    if (spend > 0) parts.push(`costs ${money(spend)} of the bank`);
    if (spend < 0) parts.push(`frees ${money(-spend)}`);
    return `${parts.join("; ")}.`;
  });

  if (week.transferCostPoints > 0) {
    swaps.push(
      `Four points a head for going beyond the free transfer, ${week.transferCostPoints} in total, already taken off the expected haul.`,
    );
  }
  return swaps.join(" ");
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
      `${player.name} is a ${money(player.priceTenths)} ${player.position} sitting on the bench, which is a lot of money to leave out.`,
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
    `The eleven averages ${mean.toFixed(1)} out of five on fixture difficulty, which is ${DIFFICULTY_WORD[Math.round(mean)] ?? "even"}.`,
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
    parts.push(
      `${named} ${hardest.length === 1 ? "is" : "are"} rated four or worse, and ${hardest.length === 1 ? "is" : "are"} kept because the projection already prices that fixture in rather than despite it.`,
    );
  }
  if (blanks.length > 0) {
    parts.push(
      `${blanks.map((player) => player.name).join(", ")} ${blanks.length === 1 ? "has" : "have"} no fixture and ${blanks.length === 1 ? "scores" : "score"} nothing.`,
    );
  }
  return parts.join(" ");
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
      `${week.captain.name} is ${Math.round(share * 100)}% of the expected haul, so the week turns on him more than on anyone else.`,
    );
    if (runnerUp) {
      // Naming the runner-up is what makes the armband arguable rather than
      // asserted, and it is usually a defender because the 2025/26 defensive
      // contribution route pays them for work that never used to score.
      parts.push(
        `He is picked over ${runnerUp.player.name} by ${points(captain - runnerUp.score)} a match on the highest expected score, which is the only armband rule that survived testing: ${CAPTAINCY_VERDICT}`,
      );
    }
  }

  const thin = week.starters.filter((player) => scoreOf(week, player) < 2);
  if (thin.length > 0) {
    parts.push(
      `${thin.map((player) => player.name).join(", ")} ${thin.length === 1 ? "is" : "are"} projected under two points and ${thin.length === 1 ? "is" : "are"} in the eleven only because the alternative is worse.`,
    );
  }

  parts.push(...benchedPremiumReasons(week));

  const rated = week.starters
    .map((player) => week.difficulty[player.club] ?? null)
    .filter((rating): rating is number => rating !== null);
  if (rated.length > 0) {
    const hard = rated.filter((rating) => rating >= 4).length;
    const soft = rated.filter((rating) => rating <= 2).length;
    parts.push(
      `${soft} of the eleven have a soft tie and ${hard} a hard one, which is what the projection is already priced against.`,
    );
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

    const opening = `${player.name} costs ${money(player.priceTenths)} and is benched on ${points(benched)} projected`;

    if (blank) {
      return `${opening}, because he has no fixture this week and scores nothing whatever he is worth.`;
    }
    if (!picked) {
      return `${opening}; no ${player.position} is started ahead of him, so the bench is a squad-rule consequence rather than a call on him.`;
    }
    const gap = picked.score - benched;
    if (gap <= 0) {
      // Started anyway: the eleven is a formation, not a ranking.
      return `${opening}, which is ${points(-gap)} above ${picked.starter.name} at ${points(picked.score)}. He is out on formation rather than on projection — the shape that fits the rest of the eleven cannot carry both.`;
    }
    return `${opening} against ${picked.starter.name} on ${points(picked.score)}, a gap of ${points(gap)}${fixture ? ` with ${player.name} facing ${fixture}` : ""}. Price does not start a player; the projection does, and paying for him is a judgement about the rest of the season rather than this week.`;
  });
}

/** The chip line, or an honest statement that none is due. */
export function chipReason(chip: ChipCall | null): string {
  return chip ? `${chip.chip} — ${chip.note}.` : "None this week.";
}
