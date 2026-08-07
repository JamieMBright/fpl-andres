import { useState } from "react";

import { projectionSeason } from "../state/squad-projection";

/**
 * The pipeline, end to end, so a reader can check each step rather than the
 * conclusion.
 *
 * The methodology prose explains what the model believes. This explains what it
 * *does*, in order, with a worked example carried through every stage so the
 * arithmetic can be followed by hand. A reader who disagrees can then name the
 * step they disagree with, which is a far more useful conversation than
 * disagreeing with a projected total.
 *
 * Detail lives behind each step rather than on the page, because a chart that
 * shows everything at once is read as decoration. The summary line is what the
 * step does; opening it gives the inputs, the rule and the caveat.
 */

interface Stage {
  id: string;
  title: string;
  /** One line: what comes out of this step. */
  summary: string;
  /** The worked example, carried through the whole chart. */
  example: string;
  /** What the step actually does, in enough detail to argue with. */
  detail: string;
  /** Where it can be wrong. Never empty: every step has a failure mode. */
  caveat: string;
}

const STAGES: Stage[] = [
  {
    id: "sources",
    title: "1 · Sources",
    summary: "FPL for prices, squads and fixtures. Understat for shot quality.",
    example:
      "Guéhi: 35 appearances, 3,105 minutes, 6 yellows, £6.0m today, Manchester City.",
    detail:
      "Only what FPL publishes, plus Understat joined on a hand-checked crosswalk. Prices and availability are today's; the scoring record is last completed season. Nothing is scraped from a competitor and no projection from another model is used as an input.",
    caveat:
      "A player with no Premier League record — a promoted-club debutant, or an arrival from another league — has no row at all. He is left out rather than given a positional average, so the pool is smaller than the game.",
  },
  {
    id: "minutes",
    title: "2 · Minutes first",
    summary:
      "Chance of appearing, and chance of lasting an hour, before any scoring.",
    example: "Guéhi: 73% start rate, 71 expected minutes.",
    detail:
      "Appearances are recency-weighted on a four-gameweek half-life and shrunk toward a positional prior in proportion to how little he has played. One observation per fixture, so a double gameweek counts twice rather than being summed and capped. A published zero chance of playing makes him unavailable, not doubtful.",
    caveat:
      "P(60 minutes given a start) and P(cameo given benched) still default where a player has never done one of the two. That is declared as an `assumed_conditional` reason code rather than hidden.",
  },
  {
    id: "rates",
    title: "3 · Fourteen scoring routes",
    summary:
      "Per-90 rates for every way FPL pays, each shrunk toward the league.",
    example:
      "Guéhi per match: 1.45 appearance, 1.16 clean sheet, 0.67 attacking, 0.48 defensive actions, 0.32 bonus, −0.24 conceding, −0.14 cards.",
    detail:
      "Goals, assists, clean sheets, appearances, saves, cards, own goals, penalties saved and missed, goals conceded, bonus and defensive contribution. Every rate is shrunk toward a measured per-appearance league average by position, so two hundred minutes and two goals does not project as a goal a game.",
    caveat:
      "Defensive contribution is 7.5% of all points awarded and did not exist before 2025/26, so it has one season of evidence behind it and no more.",
  },
  {
    id: "fixture",
    title: "4 · The fixture, per route",
    summary:
      "One difficulty number is wrong. Each route gets its own multiplier.",
    example:
      "Guéhi at home to Bournemouth, rated 1.0 of 5 — the softest tie of the week.",
    detail:
      "Opponent strength is measured from results already played, shrunk toward the league mean on a ten-match prior, and clamped so no single fixture moves a projection by more than about a factor of two. A hard fixture lowers a clean sheet and raises saves and defensive actions, so a keeper facing the champions is not written off.",
    caveat:
      "A promoted club has no measured strength. Fixtures against them are rated as average, which is a guess dressed as a measurement, and it is the largest single soft spot in the fixture model.",
  },
  {
    id: "points",
    title: "5 · Expected points",
    summary: "Rates times minutes times fixture, summed over the routes.",
    example: "Guéhi: 3.59 points per match, ceiling 10 on his best afternoon.",
    detail: `Routes are summed, then a suspension derate is applied from his booking rate over the next five matches. The ceiling is his ninetieth-percentile match in ${projectionSeason}, which is what an armband or a chip is played for.`,
    caveat:
      "The model under-predicts in every season by 0.11 to 0.20 points per player per gameweek. That is systematic, not noise, and it is the clearest open fault in the calibration.",
  },
  {
    id: "squad",
    title: "6 · The fifteen",
    summary: "Best legal squad inside £100.0m, by exact search where it fits.",
    example:
      "Raya keeps, Gabriel and O'Reilly at the back, Fernandes and Thiago up front — £100.0m spent, £0.0m banked.",
    detail:
      "Fifteen players, at most three per club, and a formation the eleven can legally fill. Search is a cheapest-squad seed, then single swaps, then paired swaps — two out and two in — because an upgrade you cannot afford alone is paid for by selling elsewhere, and one swap at a time can never express that.",
    caveat:
      "The opening squad still scores a fifteen on total points over its horizon and picks one eleven, so rotation is invisible to it: two keepers alternating to take the softer fixture score the same as one played twice.",
  },
  {
    id: "transfers",
    title: "7 · Transfers, seven weeks at a time",
    summary:
      "Overlapping exact solves. Seven gameweeks each, the first three committed.",
    example:
      "A club with five soft fixtures then five hard ones is sold before the turn, not after it.",
    detail:
      "Each window is a mixed-integer program solved to proven optimality: squad, eleven, captain, transfers, bank and the free-transfer ledger together. Weeks past the commit boundary count at half weight. Bank flow is exact, so saving two weeks to afford a premium is priced rather than approximated.",
    caveat:
      "Seven is the longest window this solver settles reliably. Eight was tried and withdrawn: it could not prove its tie-break inside the time budget and failed the publish outright.",
  },
  {
    id: "chips",
    title: "8 · Chips",
    summary: "Every week screened cheaply, the best few solved exactly.",
    example:
      "Bench Boost where the bench is strongest; Triple Captain on the biggest ceiling.",
    detail:
      "Every legal week is scored by a cheap screen. The best three per half are then re-planned exactly — the whole season resolved around each rebuild — plus every legal pairing across the halves. Whichever week wins the exact solve is the one played, even if the screen ranked it second.",
    caveat:
      "Three per half is a time budget, not a proof that the fourth-ranked week could not win. And a Wildcard repairs drift, which a projection with no injuries, form or price changes barely has.",
  },
  {
    id: "published",
    title: "9 · What you read",
    summary: "Every gameweek, with the confidence falling as it reaches out.",
    example:
      "GW1 firm; gameweeks 2 to 8 projected; everything after that provisional.",
    detail:
      "Firm means prices, availability and fixtures are all observed and only the points are projected. Projected means inside the horizon this repository has measured. Provisional means fixtures are known and almost nothing else is — read the shape, not the names.",
    caveat:
      "The plan is solved once and published. Nothing re-reads the evidence after gameweek one, so early-season minutes — the input every rate scales off — do not yet correct it.",
  },
];

export function MethodFlow() {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section className="method-flow" aria-labelledby="method-flow-title">
      <h2 id="method-flow-title">The pipeline, step by step</h2>
      <p className="method-flow-lede">
        One player carried the whole way through, so the arithmetic can be
        followed by hand. Open a step for what it actually does and where it can
        be wrong — every step has a caveat, because every step can be wrong.
      </p>

      <ol className="method-flow-list">
        {STAGES.map((stage, index) => (
          <li className="method-flow-step" key={stage.id}>
            <article>
              <h3>{stage.title}</h3>
              <p className="method-flow-summary">{stage.summary}</p>
              <p className="method-flow-example mono">{stage.example}</p>

              <button
                aria-expanded={open === stage.id}
                className="method-flow-toggle"
                onClick={() => {
                  setOpen(open === stage.id ? null : stage.id);
                }}
                type="button"
              >
                {open === stage.id
                  ? "Hide the detail"
                  : "How, and where it fails"}
              </button>

              {open === stage.id ? (
                <div className="method-flow-detail">
                  <p>{stage.detail}</p>
                  <p className="method-flow-caveat">
                    <strong>Where it can be wrong.</strong> {stage.caveat}
                  </p>
                </div>
              ) : null}
            </article>
            {index < STAGES.length - 1 ? (
              <span aria-hidden="true" className="method-flow-arrow">
                ↓
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
