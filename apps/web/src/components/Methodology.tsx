import { Link } from "react-router-dom";

import { projectionSeason } from "../state/squad-projection";

/**
 * How the projection is built, in enough detail to be argued with.
 *
 * Every number quoted here is one this repository measured. Where a method
 * loses, the loss is stated rather than omitted, because a methodology page
 * that only reports wins is marketing.
 */
export function Methodology() {
  return (
    <div className="method-body">
      <p className="lede">
        All forecasts are wrong. Some are useful. This page says exactly how
        mine is built, what it was tested against, and where it loses — so you
        can decide whether it is useful to you rather than taking my word for
        it.
      </p>

      <section aria-labelledby="method-points">
        <h2 id="method-points">Every way a point is scored</h2>
        <p>
          Most public models price goals, assists, clean sheets and appearances,
          then stop. That misses roughly a fifth of the points in the game. I
          price all fourteen routes: appearances, goals, assists, clean sheets,
          goals conceded, saves, penalties saved, penalties missed, own goals,
          yellow cards, red cards, bonus, and the defensive-contribution points
          introduced for 2025/26.
        </p>
        <p>
          Defensive contribution alone was <strong>7.5%</strong> of all points
          scored in {projectionSeason}. A model that ignores it does not
          slightly misprice defenders; it misprices the whole position.
        </p>
        <p className="method-proof">
          <strong>How I know the pricing is right.</strong> I rebuilt every
          player&rsquo;s realised points from the component columns alone and
          compared the total against what FPL actually awarded. For{" "}
          {projectionSeason} the reconstruction came to <strong>34,383</strong>{" "}
          against an actual <strong>34,382</strong> — a one-point discrepancy
          across a whole season. For 2024/25, 27,353 of 27,605 player-gameweeks
          match exactly; every remaining row is an Assistant Manager, which is a
          chip and not a footballer.
        </p>
      </section>

      <section aria-labelledby="method-minutes">
        <h2 id="method-minutes">Minutes first, points second</h2>
        <p>
          A player who does not play scores nothing, so minutes are modelled
          before anything else: the probability of appearing at all, and the
          probability of lasting an hour. Scoring rates are then applied per
          ninety minutes and scaled by the minutes expected.
        </p>
        <p>
          Rates are shrunk toward the league average for that position, weighted
          by how much the player has actually played. A striker with two hundred
          minutes and two goals is not projected at a goal a game.
        </p>
        <p>
          The minutes model is calibrated: across the corpus, the predicted
          probability of appearing sits within 0.07 of the observed rate, and
          the probability of reaching sixty minutes is close to exact.
        </p>
      </section>

      <section aria-labelledby="method-blend">
        <h2 id="method-blend">Two views, blended</h2>
        <p>
          The component reconstruction is indirect: it accumulates a little
          error across fourteen routes. A player&rsquo;s recent scoring is
          direct but noisy. Neither alone is best. I weight the components at{" "}
          <strong>0.8</strong> and the last five gameweeks at{" "}
          <strong>0.2</strong>.
        </p>
        <p>
          That weight was tested independently in each of seven seasons and came
          out between 0.7 and 0.8 every time, including in the three seasons
          held back from the original fit. It is not tuned to the seasons it is
          reported against.
        </p>
      </section>

      <section aria-labelledby="method-fixtures">
        <h2 id="method-fixtures">Fixtures change routes, not totals</h2>
        <p>
          A hard fixture does not scale a player down uniformly. It makes a
          clean sheet less likely, and it makes saves and defensive actions{" "}
          <em>more</em> likely. Each scoring route carries its own adjustment,
          so a goalkeeper facing the champions is not simply written off.
        </p>
        <p>
          Team strength is estimated from results already played, shrunk toward
          the league mean with a ten-match prior, and clamped so no single
          fixture can swing a projection more than a factor of about two.
        </p>
      </section>

      <section aria-labelledby="method-horizon">
        <h2 id="method-horizon">Planning further than Saturday</h2>
        <p>
          A transfer is a commitment. Projections are produced at one, three,
          five and seven gameweeks ahead, from one fixed reading of form —
          projecting future form from future results would be a leak, so only
          the fixture list varies across the ladder.
        </p>
        <p>
          The ladder measurably beats repeating a one-week projection: rank
          correlation improves by 0.012 at three weeks, 0.019 at five, and 0.020
          at seven. It matters less than you might hope, because 83% of the top
          thirty is the same either way.
        </p>
      </section>

      <section aria-labelledby="method-fair">
        <h2 id="method-fair">Testing it fairly</h2>
        <p>
          The first time I scored the model against a simple &ldquo;last five
          gameweeks&rdquo; baseline, the baseline won. That result was an
          artefact. Each method was being scored on the players <em>it</em>{" "}
          could rank, and the baseline could rank around 730 players — including
          some 350 fringe players who trivially score zero — while the model,
          which refuses to project without evidence, could rank 380. Ranking
          obvious zeroes correctly inflates a correlation.
        </p>
        <p>
          Every method is now scored on the identical population: only players
          all four methods can rank. On that basis the model beats the baseline
          in all four seasons tested. The bug is described here rather than
          quietly fixed because the first number I published was wrong.
        </p>
      </section>

      <section aria-labelledby="method-loses">
        <h2 id="method-loses">Where it loses</h2>
        <ul className="method-losses">
          <li>
            In a simulated mini-league over 2024/25, a manager who simply chased
            recent form <strong>beat</strong> the advised policy by 38 points.
            It won the other three seasons tested; it does not win every season.
          </li>
          <li>
            Playing to your mini-league rank rather than to raw points is worth
            about sixteen points a season, and lost in one season of four. It is
            a weak effect, and I say so rather than dressing it up as an edge.
          </li>
          <li>
            The simulation starts at gameweek seven, because earlier gameweeks
            have too little evidence. Its totals cover 31 or 32 weeks, not 38,
            and should never be read as season scores.
          </li>
          <li>
            Chip timing reads the final fixture list, which confirms double
            gameweeks earlier than a real manager would know them. The simulated
            chips are therefore better timed than yours could be.
          </li>
        </ul>
      </section>

      <section aria-labelledby="method-silent">
        <h2 id="method-silent">Where it says nothing</h2>
        <p>
          A promoted-club debutant, or an arrival from another league, has no
          Premier League evidence. I leave them out. A positional average would
          look like knowledge and would not be knowledge.
        </p>
        <p>
          The same applies between seasons. Until a gameweek of 2026/27 has been
          played there is no form to measure and no fixture to weight, so the
          only figure I publish is what each player returned per match last
          season, labelled as exactly that.
        </p>
      </section>

      <p className="method-footnote">
        The full scoring record, season by season and including the seasons I
        lose, is <Link to="/calibration">kept score of here</Link>.
      </p>
    </div>
  );
}
