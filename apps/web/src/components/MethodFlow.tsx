import { useState } from "react";

import { BarChart, type Bar } from "./MethodChart";
import { projectionSeason } from "../state/squad-projection";

/**
 * The pipeline, end to end, so a reader can check each step rather than the
 * conclusion.
 *
 * Every step names the numbers it starts from, the arithmetic it does to them
 * and the constants it uses, because a step you cannot recompute by hand is a
 * step you have to take on trust. A different player carries each step: one
 * player carried the whole way reads as a worked example that happened to come
 * out well.
 *
 * Detail lives behind each step rather than on the page, because a chart that
 * shows everything at once is read as decoration. The summary line is what the
 * step does; opening it gives the chart, the arithmetic, the constants and the
 * caveat.
 */

interface Stage {
  id: string;
  title: string;
  /** One line: what comes out of this step. */
  summary: string;
  /** The worked example for this step, in plain words. */
  example: string;
  /** The arithmetic, written out with the actual numbers. */
  arithmetic?: string;
  /** The numbers this step uses, drawn rather than listed. */
  chart?: { caption: string; unit: string; bars: Bar[] };
  /** Every constant this step depends on, with its value and why it is that. */
  constants?: { name: string; value: string; why: string }[];
  /** What the step actually does, in enough detail to argue with. */
  detail: string;
  /** Where it can be wrong. Never empty: every step has a failure mode. */
  caveat: string;
}

const STAGES: Stage[] = [
  {
    id: "sources",
    title: "1 · Where the numbers come from",
    summary:
      "Three sources. FPL for prices, squads and fixtures. Understat for shot quality. Bookmakers for what a match is expected to look like.",
    example:
      "James Trafford arrives with four Premier League appearances to his name. That is the whole of his record here — not a small sample of a bigger one, the entire thing.",
    detail:
      "What FPL publishes, plus Understat joined on a crosswalk checked by hand rather than matched on name, plus free multi-bookmaker prices from football-data.co.uk. Prices and availability are today's. The scoring record is last completed season. Nothing is scraped from another FPL site and no projection from another model is used as an input, so an error here is mine and traceable.",
    constants: [
      {
        name: "Odds refresh",
        value: "daily, plus Friday evening",
        why: "Fixtures now land on every day of the week, so a twice-weekly grab would price a midweek round off a stale scrape. It runs on a hosted runner rather than my machine, because this network blocks every price host at the TLS handshake.",
      },
      {
        name: "Odds used",
        value: "pre-match, never closing",
        why: "Closing prices are sharper and unusable: the FPL deadline falls 90 minutes before the first kickoff, and team news moves prices after it. Fitting on closing prices would score information no manager could have had.",
      },
    ],
    caveat:
      "A player with no Premier League record at all — a promoted-club debutant, an arrival from abroad — gets no row. He is left out rather than given a positional average, so the pool this model chooses from is smaller than the game. You will not see him suggested, and that is a limitation rather than a judgement on him.",
  },
  {
    id: "minutes",
    title: "2 · How likely he is to play, before anything else",
    summary:
      "Two probabilities: does he appear, and does he last the hour that pays two points.",
    example:
      "Trafford started 4 of his last 19 available gameweeks. At face value that is a 21% start rate. He has played so little that the number is barely evidence, so it is pulled most of the way back toward what a typical goalkeeper does.",
    arithmetic:
      "Recent gameweeks count for more than old ones. A match 4 gameweeks ago carries half the weight of last week, 8 gameweeks ago a quarter, 16 gameweeks ago a sixteenth. Trafford's starts weight to 0.212. Then the shrink: the fewer matches behind a number, the further it is dragged toward the positional average.",
    chart: {
      caption: "Weight given to an appearance, by how long ago it was",
      unit: "share of a fresh observation",
      bars: [
        { label: "This gameweek", value: 1.0, shown: "1.00" },
        { label: "2 gameweeks ago", value: 0.841, shown: "0.84" },
        { label: "4 gameweeks ago", value: 0.5, shown: "0.50" },
        { label: "8 gameweeks ago", value: 0.25, shown: "0.25" },
        { label: "16 gameweeks ago", value: 0.063, shown: "0.06" },
      ],
    },
    constants: [
      {
        name: "Half-life",
        value: "4 gameweeks",
        why: "A month is roughly how long a change of role — a new manager, a returning first choice — takes to show up in team sheets. Shorter and one rotation looks like a drop; longer and a genuine drop takes half a season to register.",
      },
    ],
    detail:
      "One observation per fixture, so a double gameweek counts as two chances to play rather than being summed into one and capped. A published zero chance of playing makes a player unavailable, not merely doubtful. Everything downstream is multiplied by these two probabilities, which is why they come first: a brilliant rate on a bench is worth nothing.",
    caveat:
      "The chance of lasting 60 minutes given a start, and the chance of a cameo given a benching, still fall back to a default where a player has never done one of the two. That fallback is written into the output as an `assumed_conditional` reason code rather than quietly folded in.",
  },
  {
    id: "rates",
    title: "3 · Fourteen ways FPL pays, each priced separately",
    summary:
      "A per-90 rate for each scoring route, every one pulled toward the league average.",
    example:
      "Gabriel, £8.0m, projects 4.93 points a match. That single number is fourteen smaller numbers added up, and the two that dominate it are ones he cannot influence much on the day: turning up, and his side keeping a clean sheet.",
    chart: {
      caption: "Gabriel's 4.93 points a match, by route",
      unit: "points per match",
      bars: [
        { label: "Appearance", value: 1.72 },
        { label: "Clean sheet", value: 1.44 },
        { label: "Defensive actions", value: 0.79 },
        { label: "Goals and assists", value: 0.61 },
        { label: "Bonus", value: 0.53 },
        { label: "Goals conceded", value: -0.11 },
        { label: "Cards", value: -0.05 },
      ],
    },
    detail:
      "The full fourteen are goals, assists, clean sheets, appearances, saves, yellow cards, red cards, own goals, penalties saved, penalties missed, goals conceded, bonus, defensive contribution and the appearance-over-60 top-up. Each is a rate per 90 minutes measured from last season, then shrunk: a rate built on 200 minutes is dragged hard toward the positional average, a rate built on 3,000 minutes is barely moved.",
    arithmetic:
      "Shrinkage is a weighted average of what he did and what his position does. The weight on his own record is minutes ÷ (minutes + prior). At the 900-minute prior, a player with 900 minutes is exactly half his own record and half the league's; at 3,000 minutes he is 77% his own.",
    constants: [
      {
        name: "Shrinkage prior",
        value: "900 minutes",
        why: "Ten full matches. Below that, two goals in a purple patch would otherwise project as a goal a game — the single most common way a points model embarrasses itself.",
      },
    ],
    caveat:
      "Defensive contribution is 7.5% of every point the game awards and did not exist before 2025/26. It therefore has exactly one season of evidence behind it. Anywhere it is large — Gabriel's 0.79 is large — the uncertainty on it is wider than on anything else in that chart.",
  },
  {
    id: "fixture",
    title: "4 · The fixture, priced route by route",
    summary:
      "A single difficulty number is wrong for this game. Each route gets its own multiplier.",
    example:
      "Tarkowski, £6.0m, 4.33 a match. Send him to face a strong attack and the same fixture moves his routes in opposite directions: his clean sheet gets less likely, his blocks and clearances get more likely, and his goalkeeper's saves get much more likely. One number cannot say that.",
    chart: {
      caption: "What a hard away fixture does to each of Tarkowski's routes",
      unit: "multiplier, where 1.00 is an average opponent",
      bars: [
        { label: "Saves (his keeper)", value: 1.38 },
        { label: "Goals conceded", value: 1.34 },
        { label: "Defensive actions", value: 1.21 },
        { label: "Appearance", value: 1.0, shown: "1.00" },
        { label: "Clean sheet", value: 0.61 },
      ],
    },
    detail:
      "Opponent strength is measured from matches already played, shrunk toward the league mean on a ten-match prior, and then clamped so no single fixture can move a projection by more than about a factor of two. The clamp matters: an unclamped ratio built on a handful of matches will happily claim a fixture is six times harder than average, which is never true.",
    arithmetic:
      "The bookmaker feed is a second, independent route to the same quantity, refreshed daily and joined onto clubs by FPL code. A correct-score market would give the clean sheet directly, and nobody sells one free — so it is reconstructed. The sum of two independent Poissons is Poisson, so total goals is Poisson in the sum of the two sides' expected goals, and the over/under 2.5 market pins that sum exactly. The 1X2 market then splits it, fitted on the ratio of home wins to away wins rather than through the draw. Both means in hand, the clean sheet is the Poisson zero: P(0 conceded) = e raised to minus the opponent's expected goals. Every scoreline follows too, so the market that could not be bought is reconstructed.",
    constants: [
      {
        name: "Opponent prior",
        value: "10 matches",
        why: "Roughly a quarter-season. Enough that a club's early run of easy fixtures is not mistaken for the club being strong.",
      },
      {
        name: "Clamp",
        value: "0.5× to 2.0×",
        why: "The widest genuine best-against-worst, home-or-away swing measured in the corpus. Beyond it the number is an artefact of a small sample rather than a property of the fixture.",
      },
      {
        name: "Draw residual",
        value: "published per fixture",
        why: "Independent Poisson under-prices draws, which is what Dixon-Coles exists to correct. Rather than apply a correction I have not measured on this corpus, the gap between the market's draw price and the fitted model's is published. A large one is the size of the correction being forgone.",
      },
    ],
    caveat:
      "A promoted club has no measured Premier League strength, so the history route rates fixtures against them as average. That is a guess wearing the costume of a measurement, and it is the largest soft spot in the fixture model — three of twenty clubs are promoted every year, so it touches roughly a seventh of all fixtures. The bookmaker route is the intended fix, because a market prices a promoted club on evidence I do not have. It is ingested, joined and published; what it does not yet do is override the history route in the projection, and it should not until it has beaten it on four seasons of backtest.",
  },
  {
    id: "points",
    title: "5 · Putting it together into a points figure",
    summary: "Rates × minutes × fixture, summed over the routes, then derated.",
    example:
      "Bruno Fernandes, £12.0m, 5.05 a match. He is the most expensive outfield player here and the arithmetic is the same as everybody else's — no premium adjustment, no manual nudge.",
    arithmetic:
      "For each of the fourteen routes: rate per 90 × (expected minutes ÷ 90) × that route's fixture multiplier. Add the fourteen. Then subtract the suspension derate, which is the chance he is booked into a ban over the next five matches multiplied by what those matches were worth.",
    detail: `The ceiling shown beside the projection is his ninetieth-percentile match in ${projectionSeason} — one afternoon in ten is at least that good. That is the number an armband or a Triple Captain is actually played for, and it is deliberately not the mean, because a chip is a bet on the upper tail.`,
    caveat:
      "The model under-predicts in every season measured, by 0.11 to 0.20 points per player per gameweek. That is systematic rather than noise, and it is the clearest open fault in the calibration: totals shown here are, on the evidence, slightly low. Separately, the suspension derate is charged against a single week even though the risk is spread over five, which flatters that week's neighbours.",
  },
  {
    id: "squad",
    title: "6 · Choosing the fifteen",
    summary:
      "The best legal squad inside £100.0m, found by searching swaps rather than guessing.",
    example:
      "The opening squad takes Raya at £6.0m and Kelleher at £5.0m rather than one £5.5m keeper. Kelleher rates 3.34 a match to Raya's 3.29 and starts 88% of the time, so the pair is not a first choice and a spare — it is two keepers who both play, alternating onto whichever has the softer week.",
    detail:
      "The squad is scored by adding up what its starting eleven is expected to score in each gameweek of the horizon, one gameweek at a time, picking the best legal eleven fresh in every one. Scoring it gameweek by gameweek is what makes rotation visible: a pair who alternate score more across ten weeks than one keeper played ten times, and a model that scored the squad once against a season total could never see the difference.",
    arithmetic:
      "Search runs in three passes. First a cheapest-legal-squad seed. Then single swaps: take one player out, put one in, keep it if the total rises. Then paired swaps — two out and two in together, over the 8 highest-scoring and 8 cheapest candidates per position. The paired pass is what pays for an upgrade you cannot afford on its own: you sell elsewhere to fund it, and no sequence of single swaps can express that, because every intermediate step is illegal or worse.",
    chart: {
      caption: "What each search pass is worth, measured on the same objective",
      unit: "projected season points",
      bars: [
        { label: "Seed + single swaps", value: 2181, shown: "2181.0" },
        { label: "+ paired swaps", value: 2190, shown: "2190.1" },
      ],
    },
    constants: [
      {
        name: "Paired-swap candidates",
        value: "8 per position",
        why: "The pass is quadratic in this number. Sixteen candidates is four times the work for a gain that did not appear in testing.",
      },
      {
        name: "Squad rules",
        value: "15 players, max 3 per club, £100.0m",
        why: "The game's, not mine. Every candidate squad is checked against them and an illegal one is never scored.",
      },
    ],
    caveat:
      "This is a search, not a proof. It finds the best squad reachable by single and paired swaps from a cheap starting point, which is not guaranteed to be the best squad that exists. A move that needs three simultaneous swaps to become legal will be missed.",
  },
  {
    id: "transfers",
    title: "7 · Planning transfers seven weeks at a time",
    summary:
      "Solve seven gameweeks exactly, act on the first three, then slide the window forward.",
    example:
      "O'Reilly, £6.5m, 5.20 a match, has five soft fixtures and then five hard ones. Because the plan can see past the turn, he is sold before it rather than after — which is the whole reason for planning ahead instead of week by week.",
    detail:
      "Seven gameweeks are solved together as one problem: which fifteen to hold, which eleven to start, who captains, which transfers to make, how much to leave in the bank and how many free transfers are carried. Not solved one week at a time and stitched together — solved together, because saving a transfer this week to afford a premium next week only makes sense if both weeks are in the same problem.",
    arithmetic:
      "Only the first three gameweeks of each solve are kept and acted on. The window then slides forward three and the next seven are solved, so gameweeks 4–7 get planned twice: once as a distant tail, once as the near term with fresher information. While they are still the tail they count at half weight, because a decision seven weeks out should inform this week's transfer without dictating it.",
    chart: {
      caption:
        "One window: how much each of its seven gameweeks counts toward the decision",
      unit: "weight in the objective",
      bars: [
        { label: "GW +1 (committed)", value: 1.0, shown: "1.00" },
        { label: "GW +2 (committed)", value: 1.0, shown: "1.00" },
        { label: "GW +3 (committed)", value: 1.0, shown: "1.00" },
        { label: "GW +4 (re-solved later)", value: 0.5, shown: "0.50" },
        { label: "GW +5 (re-solved later)", value: 0.5, shown: "0.50" },
        { label: "GW +6 (re-solved later)", value: 0.5, shown: "0.50" },
        { label: "GW +7 (re-solved later)", value: 0.5, shown: "0.50" },
      ],
    },
    constants: [
      {
        name: "Window",
        value: "7 gameweeks",
        why: "The longest this solver settles reliably. Eight was tried and withdrawn: it could not prove its tie-break inside the time budget and failed the publish outright.",
      },
      {
        name: "Commit",
        value: "the first 3 gameweeks",
        why: "Everything after that is re-solved with better information before it is ever acted on, so committing it would pretend to a certainty the plan does not have. That is the commit boundary: the line between what the plan is telling you to do and what it is only using to decide.",
      },
      {
        name: "Hit",
        value: "−4 points per extra transfer",
        why: "The game's rule, read from the FPL rules page on a dated reference. It is never assumed: if that reference cannot be resolved the publish fails rather than guessing.",
      },
    ],
    caveat:
      "Across the published season the free-transfer limit binds in 19 of 38 gameweeks — the plan spends every transfer it has — and it never takes a hit. A plan that never pays 4 points is either disciplined or too cautious, and the current evidence cannot tell you which.",
  },
  {
    id: "chips",
    title: "8 · Deciding when to play the chips",
    summary:
      "Every legal week is scored cheaply, then the best few are re-planned properly.",
    example:
      "Szoboszlai, £7.0m, 3.96 a match, is the kind of player who decides a Bench Boost: the chip pays what the four benched players score, so a strong fourth-choice midfielder is worth more to it than a strong captain is.",
    arithmetic:
      "The cheap screen scores a chip in the week it would be played, without re-planning anything around it. Bench Boost scores the four bench players' expected points in that gameweek. Triple Captain scores one extra copy of the best captain's ceiling. Free Hit scores the best legal eleven for that week alone, minus the eleven already planned. Wildcard scores the best rebuilt squad over the following 8 gameweeks, minus the planned squad over the same 8. That is all a screen is: a cheap number used only to decide what to examine properly.",
    detail:
      "Every gameweek in a half is screened — no week is ruled out in advance. The best 3 per half are then re-planned exactly, meaning the whole rest of the season is re-solved around each rebuild rather than assumed unchanged, plus every legal pairing of one chip in each half. Whichever week wins the exact re-plan is the one published, even where the screen had ranked it second or third. The screen chooses what to look at; it never chooses what to play.",
    constants: [
      {
        name: "Weeks examined exactly",
        value: "3 per half",
        why: "A time budget. Each exact re-plan is a full season re-solve, and the publish already takes ten minutes.",
      },
      {
        name: "Wildcard horizon",
        value: "8 gameweeks",
        why: "How far a rebuild is credited. Beyond that the squad would have drifted for other reasons anyway, so crediting the chip for it would overstate the chip.",
      },
    ],
    caveat:
      "Three weeks per half is a budget, not a proof that the fourth-ranked week could not have won. And a Wildcard exists to repair drift — injuries, price changes, a player losing his place — which a projection built once and never updated barely has. On this evidence a Wildcard is worth about a tenth of a point, which almost certainly understates what it is worth in a real season.",
  },
  {
    id: "published",
    title: "9 · What you actually read, and how far to trust it",
    summary:
      "Every gameweek, labelled with how much of it is observed and how much is projected.",
    example:
      "Calvert-Lewin, £6.0m, 3.37 a match, appears in gameweek 30 of the plan. That is not a prediction that he will play in gameweek 30 — it is a statement about what a player of that shape is worth in that fixture, given nothing has been re-read since.",
    detail:
      "Firm means prices, availability and fixtures are all observed and only the points are projected. Projected means it sits inside the horizon this repository has measured and calibrated. Provisional means the fixtures are known and almost nothing else is — read the shape of the plan, not the names in it.",
    caveat:
      "The plan is solved once, offline, and published. Nothing re-reads the evidence after gameweek one. Early-season minutes are the input every rate scales off, and they are exactly what this cannot yet see, so the further into the season you read, the more the plan describes last season's players rather than this season's.",
  },
];

export function MethodFlow() {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section className="method-flow" aria-labelledby="method-flow-title">
      <h2 id="method-flow-title">The pipeline, step by step</h2>
      <p className="method-flow-lede">
        Nine steps from a published fixture list to the plan on the front page.
        Each names the numbers it starts from, the arithmetic it does to them
        and the constants it uses, so it can be recomputed rather than taken on
        trust. A different player carries each step. Open a step for the detail
        and for where it can be wrong — every step has a caveat, because every
        step can be wrong.
      </p>

      <ol className="method-flow-list">
        {STAGES.map((stage, index) => (
          <li className="method-flow-step" key={stage.id}>
            <article>
              <h3>{stage.title}</h3>
              <p className="method-flow-summary">{stage.summary}</p>
              <p className="method-flow-example">{stage.example}</p>

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
                  : "The arithmetic, and where it fails"}
              </button>

              {open === stage.id ? (
                <div className="method-flow-detail">
                  {stage.chart ? (
                    <BarChart
                      bars={stage.chart.bars}
                      caption={stage.chart.caption}
                      unit={stage.chart.unit}
                    />
                  ) : null}

                  {stage.arithmetic ? (
                    <p className="method-flow-arithmetic">
                      <strong>The arithmetic.</strong> {stage.arithmetic}
                    </p>
                  ) : null}

                  <p>{stage.detail}</p>

                  {stage.constants ? (
                    <dl className="method-flow-constants">
                      {stage.constants.map((constant) => (
                        <div key={constant.name}>
                          <dt>
                            {constant.name}{" "}
                            <span className="mono">{constant.value}</span>
                          </dt>
                          <dd>{constant.why}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}

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
