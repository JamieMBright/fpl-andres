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
 *
 * Written plainly and in full. Everywhere else brevity is a virtue because the
 * numbers are next to the words; here there are no numbers, so a clipped
 * answer is only an answer somebody has to ask again. Nothing on this page
 * speaks in the first person: it is a description of what a program does.
 */

interface Answer {
  q: string;
  /** One paragraph per element, so an answer can take the space it needs. */
  a: readonly string[];
  link?: { to: string; text: string };
}

const ANSWERS: readonly Answer[] = [
  {
    q: "What is this site?",
    a: [
      "Two things. First, a projection of how many FPL points each Premier League player is expected to score, rebuilt from what he did last season: minutes, goals, assists, clean sheets, saves, defensive contributions and cards, each converted to a per-90 rate and then priced with the published FPL scoring table.",
      "Second, a plan. Those per-player projections are put through the real 2026/27 fixture list, and a solver picks a squad, a starting eleven, a captain and a transfer for all 38 gameweeks inside the actual rules: £100.0m, fifteen players, no more than three from one club, one free transfer a week, four points for any transfer beyond it.",
      "No part of it is an opinion about a footballer. Every number traces back to a measurement or to a published rule.",
    ],
  },
  {
    q: "Where do I find my Team ID?",
    a: [
      "Log in to fantasy.premierleague.com and open the Points tab. The address bar will read something like fantasy.premierleague.com/entry/212279/event/1, and the number after /entry/ is the Team ID. It is usually seven digits and it never changes.",
      "It is public information. Anyone with that number can look up the squad the same way this site does, which is why it is not treated as a secret.",
    ],
  },
  {
    q: "Does my squad get sent anywhere?",
    a: [
      "The 38-gameweek solve runs in the browser, on the machine reading this page. A declared squad, bank, free transfers, chip state and corrections are read only from that browser's storage.",
      "When a transfer is declared, a write-only server copy of the Team ID, season, gameweek and swap is kept for diagnostics. It is never read back into a plan. The copy is deleted seven days after the gameweek deadline and never kept beyond thirty days; request diagnostics are deleted after thirty days.",
      "The site does ask FPL's public API for the squad belonging to a Team ID that is typed in, because that is the only way to know what is in it. That request goes through this site's own server so the browser is not calling FPL directly, and the answer is exactly what FPL already publishes to anybody who asks.",
    ],
    link: { to: "/privacy", text: "Read the privacy and data controls" },
  },
  {
    q: "Why does the plan change from one week to the next?",
    a: [
      "Because the inputs change. Prices move, players get injured, fixtures get rearranged, and the plan starts from whatever squad is owned that day. A plan that returned the same answer regardless would not be reading any of it.",
      "The parts worth acting on are the ones that survive a re-solve: which gameweeks are worth a chip, which runs of fixtures are worth holding a player through, and roughly how much of the budget should sit in premiums. Individual names more than a month out move around and are not meant to be read as commitments.",
    ],
  },
  {
    q: "Why is an obvious big name missing from the recommended squad?",
    a: [
      "Because a squad has £100.0m for fifteen players, so every pick is charged against everything it prevents. A £15.0m forward has to out-score not only the £8.0m forward who would replace him, but also the upgrades the remaining £7.0m would buy across the rest of the squad.",
      "A player can therefore be both the best footballer in the game and the wrong pick at his price. The solver is answering the second question.",
    ],
  },
  {
    q: "Why are promoted clubs barely represented?",
    a: [
      "Their players have no Premier League record to measure. The projection is built entirely from last season's Premier League data, so a player who spent it in the Championship has no per-90 rates to convert, and he is left out of the pool rather than given invented ones.",
      "Fixtures against those clubs are still rated. FPL publishes an attack and a defence strength for all twenty clubs, home and away, before a ball is kicked, and that is what a promoted opponent's difficulty is read from.",
    ],
  },
  {
    q: "How far ahead is the projection reliable?",
    a: [
      "About seven gameweeks. That is the horizon the model has been backtested over; beyond it the accuracy has not been measured, so it is not claimed.",
      "The fixture list itself is known for the whole season. What is not knowable that far out is form, injuries, price changes, transfers in and out of the league, and managerial changes. Each gameweek in the plan is labelled firm, projected or provisional so it is clear which is which.",
    ],
  },
  {
    q: "How accurate is it?",
    a: [
      "It is measured against four completed seasons and every test is published, including the ones it loses. Against the obvious baseline — a player's last five scores, averaged — it ranks better within every position in every season tested, sixteen cells out of sixteen.",
      "Against simulated managers it is less emphatic. It beats a manager who chases form in all four seasons, but by a margin that has narrowed from 228 points to 13, and in 2025/26 a manager who simply owned the most-picked players finished ahead of it.",
      "Every figure behind those statements is on the calibration page, and the sentences describing them are generated from the data rather than typed, so they cannot drift away from it.",
    ],
    link: { to: "/calibration", text: "See the calibration in full" },
  },
  {
    q: "Why does it not know about an injury I have just read about?",
    a: [
      "The per-player projection is built offline from a completed season and published as a file. It carries no news feed and no injury list, so a player ruled out this morning still appears with last season's rates.",
      "FPL's own availability flag is read for the squad shown on the plan page, so a flagged player is marked as such. But no projection is withdrawn on the basis of news, because nothing here has measured what news is worth.",
    ],
  },
  {
    q: "Can it tell me who to captain?",
    a: [
      "It will name the highest-projected player in the squad, and that rule has been tested against nine alternatives across 127 scored gameweeks. Only one alternative was measurably worse; the rest could not be told apart from it statistically.",
      "The honest summary is that captaincy is where the projection has least edge. The gap between any of these rules and simply picking the best player available on the day is far larger than the gaps between the rules.",
    ],
  },
  {
    q: "What is the site not doing?",
    a: [
      "It is not reading team news, press conferences, expected line-ups or social media. It is not modelling rotation risk in cup weeks, and it does not know that a manager has said a player needs a rest.",
      "It is not using bookmakers' prices in the projection. It is not simulating other managers' squads or your mini-league. And it is not a betting product: nothing here prices a bet or suggests one.",
    ],
  },
] as const;

const FPL_LINGO = [
  [
    "DefCon",
    "Defensive contribution. Two points in a match for reaching a threshold of defensive actions: ten for a defender, counting clearances, blocks, interceptions and tackles; twelve for a midfielder or forward, which also counts ball recoveries. Goalkeepers cannot score it. Introduced for 2025/26, where it accounted for 7.5% of all points FPL awarded.",
  ],
  [
    "xG",
    "Expected goals. Every shot is given the probability that an average player would score it, from where and how it was taken. A player's xG is the sum of those probabilities, so it measures the chances he got rather than whether they went in.",
  ],
  [
    "xA",
    "Expected assists. The same idea applied to the pass before the shot, crediting the player who created the chance whether or not the shooter finished it.",
  ],
  ["xGI", "Expected goal involvement: xG and xA added together."],
  [
    "ICT index",
    "FPL's own composite of influence (involvement in decisive moments), creativity (chances created) and threat (goal-scoring danger). It is published by FPL and is not an input to this site's projection.",
  ],
  [
    "BPS",
    "Bonus points system. A tally FPL keeps during a match for passes completed, tackles won, saves, big chances created and missed and so on. The three highest tallies in each match take 3, 2 and 1 bonus points.",
  ],
  [
    "Hit",
    "The four points charged for each transfer beyond the free ones available. Two extra transfers cost eight points.",
  ],
  [
    "Template",
    "The squad most managers converge on. Owning it moves a rank with the field rather than against it, so it protects a position more than it improves one.",
  ],
  [
    "Differential",
    "A player owned by very few managers. Owning one gains rank quickly on a return and costs little on a blank, because few rivals owned him either way.",
  ],
  [
    "EO",
    "Effective ownership. The share of squads owning a player plus the share captaining him, since a captain counts twice. It is what decides whether a haul gains or loses rank.",
  ],
  [
    "Haul",
    "An unusually large score from one player in one gameweek, conventionally double figures.",
  ],
  [
    "Wildcard",
    "A chip giving unlimited transfers in one gameweek at no cost, with the new squad kept from then on. Two are issued a season, one per half, and an unplayed first-half wildcard expires at gameweek 19.",
  ],
  [
    "Free Hit",
    "A chip that fields a completely different squad for one gameweek at no cost. At the final whistle the original squad returns exactly as it was.",
  ],
  [
    "Bench Boost",
    "A chip that scores all fifteen players for one gameweek instead of the usual eleven.",
  ],
  [
    "Triple Captain",
    "A chip that triples the captain's score for one gameweek instead of doubling it.",
  ],
  [
    "FDR",
    "Fixture difficulty rating. FPL's own one-to-five score, five being hardest. This site does not use it, because one number cannot be right for both ends of the pitch: a hard fixture means fewer clean sheets but more saves and more defensive contributions.",
  ],
  [
    "Price rise",
    "A player's price moves with how many managers are buying and selling him. When a player who has risen is sold, only half the profit is kept, rounded down to the nearest £0.1m.",
  ],
  ["Bank", "Money in the squad not currently spent on a player."],
  [
    "Team value",
    "What the fifteen would raise if all were sold, plus the bank. It is not what they cost, because of the half-profit rule on sales.",
  ],
] as const;

const SITE_WORDS = [
  [
    "Firm",
    "A gameweek already played. Every figure in it is observed rather than forecast.",
  ],
  [
    "Projected",
    "A gameweek inside the seven-gameweek horizon the model has been backtested over. The fixtures are known and the points are forecast.",
  ],
  [
    "Provisional",
    "A gameweek beyond that horizon. The fixtures are real but nothing else has been validated at that distance, so the shape of the plan carries meaning and the individual names do not.",
  ],
  [
    "Net points",
    "Expected points for a gameweek after the cost of any transfer hits has been subtracted.",
  ],
  [
    "xPts over N gameweeks",
    "Expected points added up across the next N gameweeks against the real opponents. A double gameweek counts twice and a blank counts nothing, which is what a per-match figure cannot express. Five or more is the horizon a transfer is best judged on.",
  ],
  [
    "Two-sigma curve",
    "A line two standard deviations above the average of the players at a similar x-value, measured in slices across the chart. About one player in forty clears it, and those are the ones doing something the rest of the pool at that price or workload does not.",
  ],
  [
    "Sweet spot",
    "The corner of a chart where both axes are good. It is shaded rather than outlined, because no threshold makes a player inside it different in kind from one just outside.",
  ],
  [
    "Overlooked",
    "A player who is strong on both plotted axes and owned by very few managers.",
  ],
  [
    "Vintage",
    "Which point in time a number describes. Record means the last completed season. Market means today: what a player costs now and who owns him now. The two are never blended into one figure.",
  ],
  [
    "Cohort",
    "The 2,207 managers found by sweeping every FPL entry ID who have finished inside the top 10,000 at least twice since 2021.",
  ],
  [
    "Evidence level",
    "A label carried by every recommendation recording how much of it is measured and how much inferred, so a projection built on 3,000 minutes is not presented like one built on 300.",
  ],
] as const;

function Glossary({
  entries,
  id,
  intro,
  title,
}: {
  readonly entries: readonly (readonly [string, string])[];
  readonly id: string;
  readonly intro: string;
  readonly title: string;
}) {
  return (
    <section aria-labelledby={id} className="faq-glossary">
      <h2 id={id}>{title}</h2>
      <p className="faq-intro">{intro}</p>
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
    { canonicalPath: "/faq" },
  );

  return (
    <section className="text-page faq-page">
      <p className="eyebrow">Questions</p>
      <RouteHeading>Questions and definitions.</RouteHeading>

      <p className="faq-lede">
        This is the long version. Everywhere else on the site the words are kept
        short because the numbers are next to them. Here there are no numbers,
        so nothing is abbreviated.
      </p>

      <section aria-labelledby="faq-answers-title" className="faq-answers">
        <h2 id="faq-answers-title">Common questions</h2>
        <dl>
          {ANSWERS.map((entry) => (
            <div key={entry.q}>
              <dt>{entry.q}</dt>
              <dd>
                {entry.a.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
                {entry.link ? (
                  <p>
                    <Link to={entry.link.to}>{entry.link.text}</Link>.
                  </p>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <Glossary
        entries={FPL_LINGO}
        id="faq-lingo-title"
        intro="Terms belonging to Fantasy Premier League itself. They mean the same here as anywhere else in the game."
        title="Fantasy Premier League terms"
      />
      <Glossary
        entries={SITE_WORDS}
        id="faq-mine-title"
        intro="Terms specific to this site, defined here because each appears on a chart or a plan with no room to explain itself."
        title="Terms used on this site"
      />

      <p className="faq-footnote">
        For the arithmetic behind the projection, see{" "}
        <Link to="/methodology">the method</Link>. For how accurate it has
        proved, including where it loses, see{" "}
        <Link to="/calibration">the calibration</Link>.
      </p>
    </section>
  );
}
