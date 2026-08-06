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

      <section aria-labelledby="method-captaincy">
        <h2 id="method-captaincy">On captaincy</h2>
        <p>
          The captain doubles. One call a week therefore carries two to three
          times the expected-value swing of a routine transfer, and it is the
          only decision in the game with a multiplier attached. It is also the
          one this project made without evidence for longest: take the highest
          projected scorer, and never check.
        </p>
        <p>
          Every published framework says that is wrong. None of them publishes a
          measurement, and they contradict each other, so all of them are
          written down as rules and scored on the same gameweeks, the same
          shortlist and the same ceiling. Nine theses; a tenth is the
          owner&rsquo;s own.
        </p>

        <h3>What the sources argue</h3>
        <p>
          <strong>
            Ramezani and Dinh,{" "}
            <em>
              A data-driven framework for team selection in Fantasy Premier
              League
            </em>{" "}
            (arXiv:2505.02170)
          </strong>{" "}
          make captaincy a decision variable inside the optimiser rather than a
          heuristic bolted on afterwards: maximise{" "}
          <code>&Sigma; c&#8321;x&#8321; + &Sigma; c&#8321;y&#8321;</code>{" "}
          subject to <code>&Sigma;y&#8321; = 1</code> and{" "}
          <code>y&#8321; &le; x&#8321;</code> &mdash; exactly one captain, and
          he must be starting. They also report that penalising a score by its
          own uncertainty trimmed upside without buying protection, and cite
          Bhatt&rsquo;s finding that crowd captaincy beat expert analysts.
        </p>
        <p>
          <strong>FPL Oracle</strong> works in six steps: shortlist two to four
          on expected points, compute effective ownership as{" "}
          <code>own% + own% &times; captain-rate</code>, apply your rank
          situation, check the fixture on opponent xGA rather than the published
          difficulty, derate by rotation risk as{" "}
          <code>xPts &times; P(start)</code>, and set the vice-captain
          independently at lower ownership. Their one quantitative claim is an
          indifference band: inside about 1.5 projected points the ownership
          maths favours the differential; two points clear and you captain the
          favourite regardless.
        </p>
        <p>
          <strong>FPL360</strong> leads on form with a hard floor at 2.0, argues
          that form compounds fixture quality rather than trading against it,
          and frames the whole decision as loss aversion &mdash; the template
          captain is chosen out of fear of the crowd rather than belief.
        </p>

        <h3>The mathematics, once</h3>
        <p>
          Every one of those rules is the same object: an <code>argmax</code>{" "}
          over a shortlist of some function of five quantities. Expected points{" "}
          <code>&mu;</code>, the spread <code>&sigma;</code>, the chance he
          starts <code>p</code>, ownership <code>&omega;</code>, and a rank
          state. The theses differ only in how they combine them.
        </p>
        <ul className="method-losses">
          <li>
            <strong>Expected points</strong> &mdash; <code>argmax &mu;</code>.
            The control, and what this project already did.
          </li>
          <li>
            <strong>Availability adjusted</strong> &mdash;{" "}
            <code>argmax &mu;p</code>. Seven and a half points behind an 85%
            chance of starting is worth 6.4; six and a half behind a certainty
            is worth 6.5.
          </li>
          <li>
            <strong>Upside</strong> &mdash; <code>argmax (&mu; + &sigma;)</code>
            . Doubling a mean is worth far less than doubling a haul, so the
            multiplier arguably makes this a right-tail bet rather than a point
            estimate.
          </li>
          <li>
            <strong>Robust</strong> &mdash;{" "}
            <code>argmax (&mu; &minus; &sigma;)</code>. The exact opposite, from
            the paper. Included because a comparison of only the ideas somebody
            believes in cannot say whether the winner won on merit.
          </li>
          <li>
            <strong>Differential and template</strong> &mdash;{" "}
            <code>argmax (&mu; &mp; &lambda;&omega;)</code> with{" "}
            <code>&lambda;</code> = 1.5 points per 100% owned, which is
            Oracle&rsquo;s own indifference band. Both signs are scored, because
            the backtest has no rank to condition on and a rule that is right
            only for managers in one league position must not be reported as
            right in general.
          </li>
          <li>
            <strong>Form</strong> &mdash; <code>argmax</code> recent scoring,
            refusing anyone under 2.0.
          </li>
          <li>
            <strong>Crowd</strong> &mdash; <code>argmax &omega;</code>. The
            template. Not a foil: it is what most managers do and what Bhatt
            found beat the experts.
          </li>
          <li>
            <strong>Ceiling against fixture</strong> &mdash;{" "}
            <code>argmax (&mu;&kappa; &times; f)</code>, where{" "}
            <code>&kappa;</code> is how many times his ordinary afternoon his
            ninetieth-percentile one is, and <code>f</code> the attacking
            multiplier for the fixture. This is the owner&rsquo;s own rule and
            it is a product, not a filter: a big enough ceiling tolerates a
            harder draw, an ordinary one needs a kind one. No separate home
            term, because venue is already measured inside <code>f</code> per
            club and per side, and pricing it twice would outrank the ceiling it
            is meant to modify.
          </li>
        </ul>

        <h3>How the comparison is kept honest</h3>
        <p>
          Every thesis picks from the same shortlist: the twenty-five most-owned
          players who have a realised score that gameweek. Given the whole pool
          each would captain the week&rsquo;s cheapest hat-trick and report
          skill at a decision nobody faced. The ceiling is the best captain{" "}
          <em>in that shortlist</em>, so the regret is a call somebody could
          have made.
        </p>
        <p>
          Nine rules is nine chances to win by luck, so the record reports the
          number of seasons a thesis won as well as its mean &mdash; a policy
          that wins once and loses three times got lucky, and a table sorted on
          the average alone would crown it. Nothing is tuned: where a
          coefficient is unavoidable it is the one its source proposed, used
          once and never swept.
        </p>
        <p>
          A ranked table still produces a winner whether or not one exists, so
          the ranking is not the verdict. Each thesis is paired against the
          projection week for week across every scored gameweek of all four
          seasons and the differences are resampled two thousand times. A thesis
          is reported as better only when the whole 95% interval sits above
          zero. Paired rather than pooled because both rules face the same
          fixtures in the same weeks; a blank gameweek depresses both, and
          comparing unpaired means would charge that to whichever was measured
          over more of them.
        </p>
        <p>
          <strong>So which one should you use?</strong> Whichever the interval
          on the calibration page marks as clearing zero &mdash; and if none of
          them does, the honest answer is the projection, because a lead the
          test cannot separate is not a reason to change what you do. That is a
          less disappointing answer than it sounds: the best captain available
          on the shortlist averages 15.45 points and the best thesis takes 7.12,
          so the whole argument between the ten is worth under two points a week
          while more than eight sit untouched. The gap that matters is not
          between the rules.
        </p>
        <p>
          <strong>Then learn the rule instead?</strong> Captaincy yields one
          graded observation per gameweek &mdash; about 127 across four seasons.
          Fitting six feature weights to 127 points whose week-to-week spread
          exceeds the entire range between best and worst thesis will report a
          lead in sample, and would report one on shuffled labels too. If a
          learned policy is ever added it enters as one more candidate, fit on
          seasons it is not scored on, and it has to clear the same interval
          every hand-written thesis is held to.
        </p>
        <p className="method-proof">
          <strong>One correction, on the record.</strong> The first run reported
          the two ownership rules as tested. They were not. The corpus stores
          ownership as a count of managers, of the order of a million, while
          both rules price it per percentage point &mdash; so the ownership term
          swamped every projection and the pair silently collapsed into
          &ldquo;captain the most owned&rdquo; and &ldquo;captain the least
          owned&rdquo;. The numbers looked plausible, which is the problem. Two
          tests now fail if either collapses again.
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
