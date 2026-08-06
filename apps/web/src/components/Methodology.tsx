import { Link } from "react-router-dom";

import { projectionSeason } from "../state/projection-meta";

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
        All forecasts are wrong. Some are useful. Here is how this one is built,
        what it was measured against, and the seasons it loses.
      </p>

      <section aria-labelledby="method-points">
        <h2 id="method-points">Fourteen scoring routes, all priced</h2>
        <p>
          Most public models price goals, assists, clean sheets and appearances.
          That is four routes out of fourteen and roughly a fifth of the points
          in the game left on the floor. Saves, cards, own goals, penalties
          saved and missed, goals conceded, bonus and defensive contribution are
          all priced here.
        </p>
        <p>
          Defensive contribution alone was <strong>7.5%</strong> of every point
          awarded in {projectionSeason} — more than assists. A model that skips
          it does not slightly misprice defenders. It misprices the position.
        </p>
        <p className="method-proof">
          <strong>Proof the pricing is right.</strong> Rebuilding every
          player&rsquo;s realised points from the component columns alone gives{" "}
          <strong>34,383</strong> for {projectionSeason} against an actual{" "}
          <strong>34,382</strong>. One point, across a season. In 2024/25,
          27,353 of 27,605 player-gameweeks reconcile exactly; every remaining
          row is an Assistant Manager, which is a chip and not a footballer.
        </p>
      </section>

      <section aria-labelledby="method-minutes">
        <h2 id="method-minutes">Minutes first</h2>
        <p>
          A player who does not play scores nothing, so minutes are modelled
          before anything else: the chance of appearing, and the chance of
          lasting an hour. Rates are then applied per ninety and scaled by the
          minutes expected, shrunk toward the positional average in proportion
          to how little a player has actually played. Two hundred minutes and
          two goals does not project as a goal a game.
        </p>
        <p>
          It is calibrated. Across the corpus, predicted probability of
          appearing sits within <strong>0.07</strong> of the observed rate, and
          the probability of reaching sixty minutes is close to exact.
        </p>
        <p className="method-proof">
          <strong>No minimum-minutes cutoff, and that was measured too.</strong>{" "}
          A thousand minutes is eleven full matches or seventeen cameos, and the
          season total cannot tell you which. Across six consecutive season
          pairs, season minutes and end-of-season minutes rank next
          season&rsquo;s opening starters at 0.616 and 0.605. Counting{" "}
          <em>starts</em>, and combining season-long volume with the role a
          player finished in, scores <strong>0.646</strong> and wins five of the
          six pairs. Among players a 900-minute filter would throw out, those
          who started four of the final six went on to start the next
          season&rsquo;s opening games <strong>42%</strong> of the time against{" "}
          <strong>10%</strong> for the rest — four times the rate, in all six
          pairs. A January signing who then played every match is not a fringe
          player. So there is no cutoff: minutes are recency-weighted on a
          four-gameweek half-life and the whole history is used.
        </p>
      </section>

      <section aria-labelledby="method-blend">
        <h2 id="method-blend">Two views, blended 0.8 to 0.2</h2>
        <p>
          The component reconstruction is indirect and accumulates a little
          error across fourteen routes. Recent scoring is direct and noisy.
          Components take <strong>0.8</strong>, the last five gameweeks{" "}
          <strong>0.2</strong>.
        </p>
        <p>
          That weight was fitted independently in each of seven seasons and
          landed between 0.7 and 0.8 every time, including the three held back
          from the original fit.
        </p>
      </section>

      <section aria-labelledby="method-fixtures">
        <h2 id="method-fixtures">Fixtures move routes, not totals</h2>
        <p>
          One difficulty number is wrong. A hard fixture makes a clean sheet
          less likely and makes saves and defensive actions <em>more</em>{" "}
          likely, so every route carries its own multiplier and a keeper facing
          the champions is not written off. Team strength comes from results
          already played, shrunk toward the league mean on a ten-match prior and
          clamped so no single fixture swings a projection by more than about a
          factor of two.
        </p>
      </section>

      <section aria-labelledby="method-horizon">
        <h2 id="method-horizon">Seven weeks out, not one</h2>
        <p>
          A transfer is a commitment, so projections run at one, three, five and
          seven gameweeks from a single fixed reading of form — only the fixture
          list varies, because projecting form from future results is a leak.
          The ladder beats repeating a one-week view by 0.012, 0.019 and 0.020
          on rank correlation at three, five and seven weeks. The gain is real
          and small: 83% of the top thirty is the same either way.
        </p>
      </section>

      <section aria-labelledby="method-fair">
        <h2 id="method-fair">The first test I ran was rigged, in my favour</h2>
        <p>
          Scored against a &ldquo;last five gameweeks&rdquo; baseline, the
          baseline won. The result was an artefact: each method was graded on
          the players <em>it</em> could rank, so the baseline got 730 players
          including some 350 fringe names who trivially score zero, while the
          model — which refuses to project without evidence — got 380. Ranking
          obvious zeroes correctly inflates a correlation.
        </p>
        <p>
          Every method is now graded on one identical population. On that basis
          the model wins all four seasons on error, rank correlation and top-20
          hit rate. The bug is on this page because the first number published
          was the wrong one.
        </p>
      </section>

      <section aria-labelledby="method-loses">
        <h2 id="method-loses">Where it loses</h2>
        <ul className="method-losses">
          <li>
            In a simulated 2024/25 mini-league, a manager chasing recent form{" "}
            <strong>beat</strong> the advised policy by 38 points. Advised won
            the other three seasons. It does not win every season.
          </li>
          <li>
            Playing to mini-league rank rather than raw points is worth about
            sixteen points a season and lost in one season of four. That is a
            weak effect, not an edge.
          </li>
          <li>
            The model under-predicts in every season, by 0.11 to 0.20 points per
            player per gameweek. That is systematic, not noise, and it is the
            clearest open fault in the calibration.
          </li>
          <li>
            Simulations start at gameweek seven and cover 31 or 32 weeks. They
            are not season scores. Chip timing there reads the final fixture
            list, so the simulated chips are better timed than yours could be.
          </li>
        </ul>
      </section>

      <section aria-labelledby="method-silent">
        <h2 id="method-silent">Where it says nothing</h2>
        <p>
          A promoted-club debutant or an arrival from another league has no
          Premier League evidence, so he is left out. A positional average would
          look like knowledge without being any.
        </p>
        <p>
          Between seasons the same rule applies. Until a gameweek of 2026/27 is
          played there is no form to read and no fixture to weight, so the only
          figure published is what each player returned per match last season,
          labelled as exactly that.
        </p>
      </section>

      <p className="method-footnote">
        Every season scored, including the ones lost,{" "}
        <Link to="/calibration">is kept here</Link>.
      </p>
    </div>
  );
}
