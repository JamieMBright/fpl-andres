import { Link } from "react-router-dom";

import validation from "../data/validation.json";
import {
  captaincyVerdict,
  ceilingSentence,
  thesisTable,
  whichThesisVerdict,
  type ThesisRow,
} from "../state/captaincy-verdict";
import { projectionSeason } from "../state/projection-meta";
import { InfoMarker } from "./InfoMarker";

const VERDICT_WORDS: Record<ThesisRow["verdict"], string> = {
  better: "measurably better",
  worse: "measurably worse",
  unproven: "inside the noise",
};

function signedWhole(value: number): string {
  const rounded = Math.round(value);
  return `${rounded < 0 ? "\u2212" : "+"}${String(Math.abs(rounded))}`;
}

function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

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
  const table = thesisTable(validation.captainSignificance);

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
          The captain doubles, so this one call a week swings two to three times
          what a transfer does. Every published strategy was written down as a
          rule and scored on the same gameweeks, from the same shortlist, over{" "}
          {verdict.weeks} paired gameweeks of four seasons. The column that
          matters is the last one: what a whole season of following each rule
          would have been worth against simply captaining the highest
          projection.
          <InfoMarker label="how each rule was scored">
            Every rule picks from the same shortlist — the twenty-five
            most-owned players with a realised score that week — because given
            the whole pool each would captain the week&rsquo;s cheapest
            hat-trick and report skill at a decision nobody faced. Each is then
            paired against the projection week for week and the differences
            resampled two thousand times. A rule is called better or worse only
            when its whole 95% interval sits one side of zero; anything else is
            a number the data cannot separate from luck.
          </InfoMarker>
        </p>

        <div
          aria-label="Scrollable captaincy strategy table"
          className="squad-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll this table horizontally.
          tabIndex={0}
        >
          <table aria-label="Every captaincy strategy, and what a season of it is worth">
            <thead>
              <tr>
                <th scope="col">Strategy</th>
                <th scope="col">What it does</th>
                <th scope="col">Points a season</th>
                <th scope="col">Range</th>
                <th scope="col">Verdict</th>
              </tr>
            </thead>
            <tbody>
              <tr className="is-control">
                <th scope="row">Highest projection</th>
                <td>
                  Captain the highest projected scorer. This is the control.
                </td>
                <td className="mono">&mdash;</td>
                <td className="mono">&mdash;</td>
                <td>what the plan does</td>
              </tr>
              {table.map((row) => (
                <tr key={row.label}>
                  <th scope="row">{sentenceCase(row.name)}</th>
                  <td>{row.rule}</td>
                  <td className="mono">{signedWhole(row.pointsPerSeason)}</td>
                  <td className="mono">
                    {signedWhole(row.lowPerSeason)} to{" "}
                    {signedWhole(row.highPerSeason)}
                  </td>
                  <td className={`thesis-${row.verdict}`}>
                    {VERDICT_WORDS[row.verdict]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p>
          <strong>So which one should you use?</strong> {which.lead}
          <em>{which.headline}</em>
          {which.detail}
        </p>
        <p>{ceiling}</p>
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
