import fpl500 from "../data/fpl500.json";
import { fineShare, integer } from "../format";

type Fpl500 = {
  generatedAt: string;
  catalogueSize: number;
  sweptTo: number | null;
  size: number;
  listed: number;
  settings: {
    decayPerSeason: number;
    preRulesChangeWeight: number;
    rulesChangedIn: number;
    shrinkageWeight: number;
    priorPercentile: number;
    minimumSeasons: number;
  };
  latestSeason: string | null;
  latestSeasonEntries: number | null;
  estimatedEntriesBySeason: Record<string, number>;
  minimumCoverage: number;
  portfolioEvents: number[];
  scoreAtRank: Record<string, number>;
  seasonsCounted: Record<string, number>;
  managers: {
    rank: number;
    entryId: number;
    score: number;
    seasons: number;
    bestPercentile: number;
    latestPercentile: number | null;
    latestSeason: string | null;
  }[];
};

const data = fpl500 as Fpl500;
const number = integer;

/** Top 0.031% reads better than 0.999687, and is the same number. */
function topShare(percentile: number): string {
  return fineShare.format(1 - percentile);
}

/**
 * The ranking, the thin cut through it, and the fund it has not become.
 *
 * The five hundred are real and committed. The fund is not, and the section
 * saying so quotes the reconciler's own rules rather than describing them,
 * because a page that promises a feature is worth less than one that names
 * exactly what is missing before the feature can exist.
 */
export function Fpl500Playbook() {
  const scores = Object.entries(data.scoreAtRank);
  const first = scores.at(0);
  const last = scores.at(-1);
  const spread = first && last ? Number(first[1]) - Number(last[1]) : null;
  const held = Object.entries(data.seasonsCounted);
  const captured = data.portfolioEvents.length;

  return (
    <>
      <section aria-labelledby="fpl500-what">
        <h2 id="fpl500-what">What the five hundred are</h2>
        <p>
          Every FPL entry id is public, so the register can be read rather than
          guessed at. The sweep has walked{" "}
          {data.sweptTo === null ? "part" : number.format(data.sweptTo)} of them
          so far and kept {number.format(data.catalogueSize)} managers who have
          finished inside the top ten thousand at least twice since 2021.{" "}
          {data.latestSeasonEntries === null ? null : (
            <>
              For scale, {data.latestSeason} had about{" "}
              {number.format(data.latestSeasonEntries)} entries.
            </>
          )}{" "}
          Those {number.format(data.catalogueSize)} are then ranked, and the
          first {number.format(data.size)} are FPL500.
        </p>
        <p className="mono">
          {`Swept to id ${
            data.sweptTo === null ? "—" : number.format(data.sweptTo)
          } · catalogue ${number.format(
            data.catalogueSize,
          )} · ranked ${number.format(data.size)}`}
        </p>
      </section>

      <section aria-labelledby="fpl500-score">
        <h2 id="fpl500-score">How the ranking is built</h2>
        <p>
          Rank cannot be averaged across seasons. The field grew from about{" "}
          {number.format(data.estimatedEntriesBySeason["2006/07"] ?? 0)} entries
          to {number.format(data.latestSeasonEntries ?? 0)}, so ten thousandth
          in 2007 and ten thousandth in 2026 are not the same achievement. Every
          season is therefore converted to a percentile of its own field first.
        </p>
        <ul className="plan-promises">
          <li>
            <span className="mono">{data.settings.decayPerSeason}</span> — what
            a season is worth against the one after it. Form decays.
          </li>
          <li>
            <span className="mono">{data.settings.preRulesChangeWeight}</span> —
            an extra discount on seasons before {data.settings.rulesChangedIn}.
            Defensive contributions changed what a good squad looks like, so
            earlier seasons are evidence about a different game.
          </li>
          <li>
            <span className="mono">{data.settings.shrinkageWeight}</span> — how
            hard a thin record is pulled toward the field median of{" "}
            {data.settings.priorPercentile}. Two brilliant seasons should not
            outrank twenty good ones.
          </li>
          <li>
            <span className="mono">{data.settings.minimumSeasons}</span> —
            seasons required before anyone is ranked at all.
          </li>
        </ul>
      </section>

      <section aria-labelledby="fpl500-thin">
        <h2 id="fpl500-thin">The order inside the five hundred means little</h2>
        <p>
          {first && last && spread !== null ? (
            <>
              The score runs from {first[1]} at rank {first[0]} to {last[1]} at
              rank {last[0]} — a spread of {spread.toFixed(3)} across the whole
              list. That is what shrinkage does to a population who are all, by
              construction, very good: it collapses them together. Membership is
              the signal here. The ordering within it is not, and nothing on
              this site should be built on the difference between fiftieth and
              four hundredth.
            </>
          ) : null}
        </p>
        <ul className="plan-money">
          {scores.map(([rank, score]) => (
            <li key={rank}>
              <span className="mono">#{rank}</span> — {score}
            </li>
          ))}
        </ul>
        <h3>Seasons held by the ranked five hundred</h3>
        <ul className="plan-promises">
          {held.map(([seasons, managers]) => (
            <li key={seasons}>
              <span className="mono">{seasons}</span> seasons —{" "}
              {number.format(managers)} managers
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="fpl500-head">
        <h2 id="fpl500-head">The head of the list</h2>
        <p>
          The first {data.listed} of {number.format(data.size)}. Entry ids are
          public; the rest are in{" "}
          <span className="mono">data/cohort/fpl500.json</span>.
        </p>
        <div className="squad-table-wrap">
          <table className="squad-table">
            <caption className="visually-hidden">
              The highest ranked {data.listed} managers in FPL500
            </caption>
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Entry</th>
                <th scope="col">Score</th>
                <th scope="col">Seasons</th>
                <th scope="col">Best</th>
                <th scope="col">Latest</th>
              </tr>
            </thead>
            <tbody>
              {data.managers.map((manager) => (
                <tr key={manager.entryId}>
                  <td className="mono">{manager.rank}</td>
                  <td className="mono">
                    <a
                      href={`https://fantasy.premierleague.com/entry/${manager.entryId}/history`}
                      rel="noreferrer noopener"
                      target="_blank"
                    >
                      {manager.entryId}
                    </a>
                  </td>
                  <td className="mono">{manager.score.toFixed(4)}</td>
                  <td className="mono">{manager.seasons}</td>
                  <td className="mono">{topShare(manager.bestPercentile)}</td>
                  <td className="mono">
                    {manager.latestPercentile === null
                      ? "—"
                      : topShare(manager.latestPercentile)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mono">
          Best and latest are the share of the field they finished ahead of,
          shown as how far into the top they came.
        </p>
      </section>

      <section aria-labelledby="fpl500-etf">
        <h2 id="fpl500-etf">The fund</h2>
        <p>
          The catalogue knows who is good. It does not know what they own: the
          sweep stores season ranks, not squads. Reconciling five hundred squads
          into one holding, once a gameweek, is what turns a list of entry ids
          into something a manager can actually read — an index of what the
          people who keep finishing well are collectively exposed to.
        </p>
        <p className="mono">
          {captured === 0
            ? "Nothing captured yet. No gameweek has been played."
            : `${captured} gameweeks captured.`}
        </p>
        <h3>What is already decided</h3>
        <p>
          The reconciler exists and is tested. These are its rules, and each one
          is there because the obvious alternative is wrong.
        </p>
        <ul className="plan-promises">
          <li>
            <strong>
              Coverage is floored at {fineShare.format(data.minimumCoverage)}.
            </strong>{" "}
            Five hundred requests will not all answer. Dividing by however many
            did makes the denominator move every week, and a player looks to be
            drifting when the sample drifted instead. Below the floor the
            snapshot is refused rather than published with an asterisk.
          </li>
          <li>
            <strong>A Free Hit squad is not a holding.</strong> It is a one-week
            rental and says nothing about what the manager owns, so it is
            excluded and counted separately.
          </li>
          <li>
            <strong>Triple Captain is three, Bench Boost is fifteen.</strong>{" "}
            Chips change what a squad means, not only what it scores, so
            "started" cannot be read off the bench position alone.
          </li>
          <li>
            <strong>Captaincy is not ownership.</strong> Sixty percent owned and
            forty captained is a different exposure from sixty and two.
            Effective ownership adds the armband on top, which is the number
            that decides a transfer.
          </li>
          <li>
            <strong>Intent, not outcome.</strong> Picks are read after the
            deadline and never reconciled against what happened. Auto-subs
            change what scored; they do not change what the cohort chose.
          </li>
          <li>
            <strong>Every manager counts once.</strong> Weighting by rank would
            claim this season's table predicts next week, and the section above
            is exactly why that claim cannot be made.
          </li>
          <li>
            <strong>Every snapshot pins the cohort it was taken over.</strong>{" "}
            Membership changes whenever the register is re-swept, and a series
            whose population silently changes is not a series.
          </li>
        </ul>
        <div className="cohort-caveat">
          <h3>What it still needs</h3>
          <p>
            Squads, which do not exist until a deadline has passed, and a
            scheduled capture to read them at the right moment — after the
            deadline, before the results settle. Until then this page is the
            ranking and the rules, and nothing is claimed about what the fund
            would have returned.
          </p>
          <p>
            One thing it will never tell you is whether being in FPL500 predicts
            the next season. The catalogue only contains managers who already
            cleared the bar, so the question cannot be answered from inside it.
          </p>
        </div>
      </section>
    </>
  );
}
