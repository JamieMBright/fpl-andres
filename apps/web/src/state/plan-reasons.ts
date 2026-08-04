import type { ChipCall, PlanGameweek, PlanPlayer } from "./season-plan";
import { CONFIDENCE_NOTE } from "./season-plan";

/**
 * Why the plan did what it did, in words, derived from the plan itself.
 *
 * Everything here is read off the published artifact rather than invented in
 * the browser. A card that says "trust me" is not evidence; a card that says
 * which fixture, which price and how many points is.
 */

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
        `He is picked over ${runnerUp.player.name} by ${points(captain - runnerUp.score)} a match; the model doubles the highest expected score rather than the biggest ceiling, so it will take a steady defender over a streaky forward.`,
      );
    }
  }

  const thin = week.starters.filter((player) => scoreOf(week, player) < 2);
  if (thin.length > 0) {
    parts.push(
      `${thin.map((player) => player.name).join(", ")} ${thin.length === 1 ? "is" : "are"} projected under two points and ${thin.length === 1 ? "is" : "are"} in the eleven only because the alternative is worse.`,
    );
  }

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

/** The chip line, or an honest statement that none is due. */
export function chipReason(chip: ChipCall | null): string {
  return chip ? `${chip.chip} — ${chip.note}.` : "None this week.";
}
