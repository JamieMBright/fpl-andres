import { Link } from "react-router-dom";

import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

/**
 * Everything a reader might need explained, in one place they can leave.
 *
 * The pages used to carry their own explanations inline, which meant every
 * reader paid for the questions only some of them had. Answers live here, the
 * short ones live in an info marker beside the number, and the pages get on
 * with showing the numbers.
 */

const ANSWERS = [
  {
    q: "What is this?",
    a: "A points projection for every Premier League player, and a 38-gameweek plan built from it. Every number is measured, not opinion.",
  },
  {
    q: "Where is my Team ID?",
    a: "Open your FPL points page. The number in the address bar is it.",
  },
  {
    q: "Does my squad go anywhere?",
    a: "No. The plan is solved in your browser. Nothing about your team is sent to a server.",
  },
  {
    q: "Why does the plan change every week?",
    a: "Because it should. Read the shape — the weeks worth a chip, the runs worth holding — and expect names beyond the next month to move.",
  },
  {
    q: "Why is a big name missing?",
    a: "Points per pound. A squad has £100.0m for fifteen, so a premium has to beat his replacement plus every upgrade the saving buys elsewhere.",
  },
  {
    q: "Why are promoted clubs thin?",
    a: "They have no Premier League record to measure. Fixtures against them are rated exactly average rather than guessed.",
  },
  {
    q: "How far ahead is it any good?",
    a: "Seven gameweeks. Past that the fixtures are real but the form, prices and injuries are not knowable.",
  },
  {
    q: "Is it ever wrong?",
    a: "Yes, and it is scored on it.",
    link: { to: "/calibration", text: "See the calibration" },
  },
] as const;

const FPL_LINGO = [
  [
    "DefCon",
    "Defensive contribution. 2 points for enough tackles, blocks and interceptions in a match.",
  ],
  ["xG", "Expected goals. What the chances a player took were worth."],
  ["xA", "Expected assists. Credits the pass, not the finish."],
  ["xGI", "Expected goal involvement. xG and xA together."],
  ["ICT", "FPL's own index of influence, creativity and threat."],
  [
    "BPS",
    "Bonus points system. The tally that decides who gets the 3, 2 and 1.",
  ],
  ["Hit", "4 points paid for a transfer beyond your free one."],
  ["Template", "The squad most managers own."],
  ["Differential", "A player almost nobody owns."],
  ["EO", "Effective ownership. Ownership plus the share captaining him."],
  ["Haul", "A big return, usually a double-digit gameweek."],
  ["Wildcard", "Unlimited transfers for one gameweek, no hits."],
  ["Free Hit", "One gameweek with a different squad, then yours returns."],
  ["Bench Boost", "All fifteen score for one gameweek."],
  ["Triple Captain", "Your captain scores treble instead of double."],
  ["FDR", "Fixture difficulty, 1 to 5. Higher is harder."],
  [
    "Price rise",
    "A player's value moving with demand. You keep half the profit.",
  ],
  ["Bank", "Money not in players."],
  ["Team value", "What your fifteen would sell for, plus the bank."],
] as const;

const MY_WORDS = [
  ["Firm", "Already played. Every number observed, not forecast."],
  [
    "Projected",
    "Inside the seven-gameweek horizon the model is calibrated on.",
  ],
  ["Provisional", "Beyond that horizon. Read the shape, not the names."],
  ["Net points", "Expected points after transfer hits are taken off."],
  [
    "Frontier",
    "The best available at each price. Nothing beats them on both axes.",
  ],
  ["Sweet spot", "The corner of the chart where both axes are good."],
  ["Overlooked", "Strong on both axes, barely owned."],
  [
    "Vintage",
    "Which season a number came from — last season's record, or today's market.",
  ],
  ["Cohort", "Managers who have repeatedly finished near the top."],
  [
    "Evidence level",
    "How much of a number is measured and how much is inferred.",
  ],
] as const;

function Glossary({
  entries,
  id,
  title,
}: {
  readonly entries: readonly (readonly [string, string])[];
  readonly id: string;
  readonly title: string;
}) {
  return (
    <section aria-labelledby={id} className="faq-glossary">
      <h2 id={id}>{title}</h2>
      <dl>
        {entries.map(([term, meaning]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{meaning}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function FaqPage() {
  useDocumentTitle(
    "Questions",
    "What FPL Andres is, what it cannot know, and what every term on the site means.",
  );

  return (
    <section className="text-page faq-page">
      <p className="eyebrow">Questions</p>
      <RouteHeading>Ask me anything.</RouteHeading>

      <section aria-labelledby="faq-answers-title" className="faq-answers">
        <h2 id="faq-answers-title">Quick answers</h2>
        <dl>
          {ANSWERS.map((entry) => (
            <div key={entry.q}>
              <dt>{entry.q}</dt>
              <dd>
                {entry.a}
                {"link" in entry ? (
                  <>
                    {" "}
                    <Link to={entry.link.to}>{entry.link.text}</Link>.
                  </>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <Glossary entries={FPL_LINGO} id="faq-lingo-title" title="FPL lingo" />
      <Glossary entries={MY_WORDS} id="faq-mine-title" title="Words I use" />

      <p className="faq-footnote">
        Want the arithmetic? <Link to="/methodology">How I work</Link> shows
        every step, and <Link to="/calibration">the calibration</Link> shows
        where it loses.
      </p>
    </section>
  );
}
