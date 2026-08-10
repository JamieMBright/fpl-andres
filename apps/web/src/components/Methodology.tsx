import { Link } from "react-router-dom";

import validation from "../data/validation.json";
import {
  captaincyVerdict,
  ceilingSentence,
  whichThesisVerdict,
} from "../state/captaincy-verdict";
import { projectionSeason } from "../state/projection-meta";

/**
 * How the projection is built, in enough detail to be argued with.
 *
 * Every number quoted here is one this repository measured. Where a method
 * loses, the loss is stated rather than omitted, because a methodology page
 * that only reports wins is marketing.
 *
 * The captaincy verdict is derived rather than written, because it is the one
 * claim on this page that a rerun can invert. See `captaincy-verdict.ts`.
 */
export function Methodology() {
  const verdict = captaincyVerdict(
    validation.captainSignificance,
    validation.seasons,
  );
  const which = whichThesisVerdict(verdict);
  const ceiling = ceilingSentence(verdict);
  // Every scored thesis, plus the projection they are all measured against.
  const thesisCount = validation.captainSignificance.length + 1;

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

      <section aria-labelledby="method-xpts">
        <h2 id="method-xpts">How a player gets a number</h2>
        <p>
          Every projection on this site is one arithmetic chain. It starts with
          what a footballer actually did and ends with a number for a named
          gameweek. Nothing in it is a rating anybody typed.
        </p>
        <ol className="method-chain">
          <li>
            <strong>Count what he did.</strong> Every appearance he has a record
            for, from the corpus: minutes, goals, assists, clean sheets, saves,
            cards, defensive actions. Recency-weighted on a four-gameweek
            half-life, so last April counts for more than the previous August.
          </li>
          <li>
            <strong>Turn counts into rates.</strong> Each becomes a per-ninety
            rate and is then pulled toward the league rate for his position, in
            proportion to how little he has played. Two hundred minutes and two
            goals does not project as a goal a game.
          </li>
          <li>
            <strong>Model the minutes separately.</strong> The chance he appears
            and the chance he lasts an hour, from his own start record shrunk
            the same way. Nothing else is computed until this is, because a
            player who does not play scores nothing.
          </li>
          <li>
            <strong>Price eleven routes.</strong> Each rate is multiplied by
            what FPL pays for it — appearance, goals and assists, clean sheet,
            bonus, saves, goals conceded, yellow cards, red cards, own goals,
            penalties missed, defensive contribution. That sum, per match
            against an average opponent, is the base.
          </li>
          <li>
            <strong>Bend each route by the fixture.</strong> Not the total.
            Every route gets its own multiplier for every one of the 38
            gameweeks, so a keeper facing the champions loses clean sheets and
            gains saves. A blank gameweek is a zero and a double counts twice.
          </li>
          <li>
            <strong>Add the gameweeks up.</strong> xPts5 is the next five, each
            priced against the fixture it is actually played in. No discount,
            because a reader asking what five gameweeks are worth is not asking
            the question the solver asks.
          </li>
        </ol>
      </section>

      <section aria-labelledby="method-promoted">
        <h2 id="method-promoted">Players and clubs with no record at all</h2>
        <p>
          Three promoted clubs arrive every August with no Premier League
          results, and every summer brings arrivals from other leagues. Neither
          gets a made-up rating, and neither is silently dropped.
        </p>
        <p>
          <strong>A promoted club</strong> is rated on FPL&rsquo;s own published
          strength, which it publishes for every club including the ones that
          have never played a top-flight match, normalised against the
          league&rsquo;s own mean so it sits on the same scale as a measured
          side. Where even that is missing the fallback is a deliberately soft
          prior — promoted sides have finished in the bottom three in most
          recent seasons, so the honest assumption is the unflattering one.
        </p>
        <p>
          <strong>A player with no record</strong> is described by his role
          rather than by himself. Players in this same squad list who{" "}
          <em>do</em> have a record are grouped by position and by depth rank —
          how expensive he is relative to his own club&rsquo;s players in his
          position — and the median of that group becomes his projection and his
          start rate. Fourth choice and below all mean the same thing, which is
          &ldquo;not expected to play&rdquo;. A role prior has no route split to
          give, so the whole figure sits on the one route his position is scored
          by rather than being spread into a shape nobody measured.
        </p>
        <p>
          He is marked unrated in the artifact, and the plan can still pick him,
          because somebody will own him and a plan that pretends he does not
          exist is not a plan for a real squad.
        </p>
      </section>

      <section aria-labelledby="method-market">
        <h2 id="method-market">Where a bookmaker gets a say</h2>
        <p>
          Everything above reads history. A book reads the team sheet. It knows
          a striker has lost his place, that a summer signing has taken it, and
          what the manager said on Friday — none of which is in last
          season&rsquo;s numbers. So where a market prices something this model
          also prices, the two are blended rather than one replacing the other.
        </p>
        <ul className="method-losses">
          <li>
            <strong>The match market sets the fixture.</strong> Where a book
            priced the result, the implied clean sheet and expected goals for
            each side set that gameweek&rsquo;s rungs directly, against the
            average fixture the same books priced that week. Where it did not,
            the fitted team strength stands.
          </li>
          <li>
            <strong>Scorer and assist prices move the attacking route.</strong>{" "}
            &ldquo;Anytime goalscorer&rdquo; is the chance of at least one and
            FPL pays per goal, so the price is inverted to a rate — Poisson, so{" "}
            <code>&lambda; = &minus;ln(1 &minus; P)</code> — and then divided by
            the multiplier of the gameweek it was quoted in, because the quote
            already carries its opponent and the solver is about to apply that
            opponent again. What survives is what the book thinks of the
            footballer with his opponent taken off, so a striker quoted against
            the champions is still the same striker next week against a promoted
            side, only at a bigger number.
          </li>
          <li>
            <strong>Card prices move the two card routes.</strong> A book prices
            &ldquo;to be shown a card&rdquo; without saying which colour, and
            prices reds separately on fewer fixtures. FPL pays &minus;1 and
            &minus;3, so the split decides the points: where both are quoted the
            split is the market&rsquo;s, and where only the card market is, the
            player&rsquo;s own recorded ratio of reds to cards apportions it.
          </li>
          <li>
            <strong>Who is in the market moves the start rate.</strong> A book
            opens a player market on men it expects to be available, so somebody
            missing from a squad it otherwise priced in full is the market
            saying he is not playing. Read downward only, and only where the
            book named at least eleven of that club&rsquo;s players — reading
            absence off a partial list would bench a defender because nobody
            quoted him to score.
          </li>
        </ul>
        <p>
          A price is never read twice. An earlier version read the
          anytime-scorer price as a minutes signal as well as a goals signal,
          which counted one number into goals and into every route that scales
          with minutes. That path is gone; market membership is a different
          fact, and it appears in one place.
        </p>
        <p className="method-proof">
          <strong>What it gives up.</strong> The card routes have no fixture
          multiplier, because nothing here has measured how a booking rate moves
          with the opponent — so a derby&rsquo;s quote is read as if it were an
          average fixture&rsquo;s. And every one of these blends is governed by
          a single weight that is assumed rather than fitted, because there is
          no season of kept quotes to fit it against yet. Both are bounded by
          that weight and neither is hidden.
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

      <section aria-labelledby="method-wildcard">
        <h2 id="method-wildcard">What a wildcard does to the horizon</h2>
        <p>
          A horizon is a claim about how long you will own somebody. Five
          gameweeks is the right yardstick for a squad you keep and the wrong
          one for a squad you have already decided to throw away, so a wildcard
          you have committed to ends the run every player before it is valued
          over. Tell the plan you are wildcarding in gameweek 3 and a gameweek 1
          transfer is priced on gameweeks 1 and 2 alone, however good the
          fixtures turn in gameweek 6. From the wildcard onwards the squad is
          new and gets the whole run ahead of it back.
        </p>
        <p>
          Without that, the plan happily pays a hit in August for a player it
          has been told will be sold in September, which is the specific way an
          unaware optimiser wastes a chip: it does not misplay the wildcard, it
          misplays the four weeks in front of it.
        </p>
        <p>
          A Free Hit does none of this. The squad comes straight back, so it
          changes one afternoon and nothing either side of it, and it is priced
          on that afternoon alone. A Bench Boost and a Triple Captain change no
          squad at all; they are read off the weeks already solved.
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
          shortlist and the same ceiling. {thesisCount} theses, one of which is
          the owner&rsquo;s own, each against the projection as control.
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
          {thesisCount} rules is {thesisCount} chances to win by luck, so the
          record reports the number of seasons a thesis won as well as its mean
          &mdash; a policy that wins once and loses three times got lucky, and a
          table sorted on the average alone would crown it. Nothing is tuned:
          where a coefficient is unavoidable it is the one its source proposed,
          used once and never swept.
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
          <strong>So which one should you use?</strong> {which.lead}
          <em>{which.headline}</em>
          {which.detail}
        </p>
        <p>
          That is less disappointing than it sounds. {ceiling} Until something
          closes it, take the highest projected scorer and spend the attention
          elsewhere.
        </p>
        <p>
          <strong>Then learn the rule instead?</strong> Captaincy yields one
          graded observation per gameweek &mdash; about {verdict.weeks} across
          four seasons. Fitting six feature weights to {verdict.weeks} points
          whose week-to-week spread exceeds the entire range between best and
          worst thesis will report a lead in sample, and would report one on
          shuffled labels too. If a learned policy is ever added it enters as
          one more candidate, fit on seasons it is not scored on, and it has to
          clear the same interval every rule here has so far failed to clear.
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
          A player with no Premier League record carries a role prior rather
          than a measurement, and the artifact says so on his row. It is not
          knowledge about him; it is what players at his position and depth rank
          actually do, and it should be read as the placeholder it is.
        </p>
        <p>
          Between seasons the same caution applies to everyone. Until a gameweek
          of {projectionSeason} is played there is no form to read, so every
          rate on this site is last season&rsquo;s, weighted by recency and
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
