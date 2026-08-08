import { useEffect, useState } from "react";

import { classifyFetchFailure } from "../state/fetch-failure";
import {
  commentary,
  readManagerProfile,
  type ManagerProfile,
} from "../state/manager-profile";
import {
  isProxyRefusal,
  readProxyRefusal,
  refusalRecourse,
  type ProxyRefusal,
} from "../state/proxy-refusal";

type Loaded = {
  entryId: number;
  profile: ManagerProfile | "unreadable" | "unreachable" | ProxyRefusal | null;
};

const ARCHETYPE_LABELS: Record<ManagerProfile["archetype"], string> = {
  newcomer: "Newcomer",
  elite: "Elite",
  contender: "Contender",
  spiker: "One big season",
  climber: "On the way up",
  fader: "Drifting",
  "ever-present": "Ever-present",
  regular: "Mid-table regular",
};

/** One decimal below ten percent, whole numbers above it. */
function share(percentile: number): string {
  return percentile < 10
    ? `${percentile.toFixed(1)}%`
    : `${Math.round(percentile)}%`;
}

/** Fallback bar for records FPL published without a percentage. */
function rankBar(rank: number, worst: number): number {
  if (worst <= 0) return 0;
  return Math.max(0.02, 1 - rank / worst);
}

/**
 * Colour band for a finish, on absolute thresholds rather than relative ones.
 *
 * Shading against a manager's own best would paint a mediocre career in green.
 * These are the same lines the chart draws, so the colour and the gridline
 * always agree.
 */
function bandOf(percentile: number | null): string {
  if (percentile === null) return "is-unrated";
  if (percentile <= 1) return "is-elite";
  if (percentile <= 10) return "is-strong";
  if (percentile <= 25) return "is-fair";
  return "is-weak";
}

/**
 * How often the target was hit, and how far the finishes scatter.
 *
 * Spread is the gap between the best and worst quarter of seasons, not between
 * the single best and worst: one freak year should not describe a career. It
 * answers a different question from the median — two managers can share a
 * typical finish while one is reliable and the other alternates.
 */
function countsOf(seasons: readonly { percentile: number | null }[]): {
  rated: number;
  elite: number;
  strong: number;
  spread: number | null;
} {
  const rated = seasons
    .map((season) => season.percentile)
    .filter((value): value is number => value !== null)
    .sort((left, right) => left - right);

  if (rated.length === 0) {
    return { rated: 0, elite: 0, strong: 0, spread: null };
  }

  const at = (fraction: number) =>
    rated[Math.min(rated.length - 1, Math.floor(fraction * rated.length))] ?? 0;

  return {
    rated: rated.length,
    elite: rated.filter((value) => value <= 1).length,
    strong: rated.filter((value) => value <= 10).length,
    spread: rated.length < 4 ? null : at(0.75) - at(0.25),
  };
}

export function ManagerHistory({ entryId }: { entryId: number }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    // Aborts rather than just ignoring the result: switching team quickly used
    // to leave the old request in flight, still consuming a connection and
    // still costing the proxy an upstream call nobody would read.
    const controller = new AbortController();

    async function read() {
      try {
        const response = await fetch(`/api/fpl/entry/${entryId}/history`, {
          signal: controller.signal,
        });
        // A refused or rate-limited response is not a malformed one. Handing
        // null to the parser made every failed fetch read as "FPL changed
        // shape", which blames the wrong thing and suggests the wrong fix.
        if (!response.ok) {
          // The proxy has already named the upstream status and classified it.
          // Repeat that rather than replacing it with a vaguer sentence.
          setLoaded({
            entryId,
            profile:
              readProxyRefusal(await response.json().catch(() => null)) ??
              "unreachable",
          });
          return;
        }
        setLoaded({
          entryId,
          profile: readManagerProfile(await response.json()),
        });
      } catch (error) {
        if (classifyFetchFailure(error).kind === "aborted") {
          return;
        }
        setLoaded({ entryId, profile: "unreachable" });
      }
    }

    void read();
    return () => {
      controller.abort();
    };
  }, [entryId]);

  // Derived rather than stored, so changing team never shows the old record.
  const ready = loaded !== null && loaded.entryId === entryId;

  if (!ready) {
    return (
      <section
        className="manager-history"
        aria-labelledby="record-title"
        aria-busy="true"
      >
        <h2 id="record-title">Your record</h2>
        {/* Every other loading and empty state on the site is
            a status region; these two were plain paragraphs, so a screen
            reader was told nothing when the record arrived or turned out not
            to exist. */}
        <p className="mono" role="status">
          Reading your history…
        </p>
      </section>
    );
  }

  if (loaded.profile === "unreachable") {
    return (
      <section className="manager-history" aria-labelledby="record-title">
        <h2 id="record-title">Your record</h2>
        <p role="status">
          I could not reach FPL for your history just now, so I am showing you
          nothing rather than a guess. Your record is intact; this is a
          connection, not a verdict.
        </p>
      </section>
    );
  }

  if (isProxyRefusal(loaded.profile)) {
    const refusal = loaded.profile;
    return (
      <section className="manager-history" aria-labelledby="record-title">
        <h2 id="record-title">Your record</h2>
        <p role="status">
          <span className="mono">{refusal.said}</span>{" "}
          {refusalRecourse(refusal.reason)} Your record is intact; I am showing
          you nothing rather than a guess.
        </p>
      </section>
    );
  }

  if (loaded.profile === "unreadable") {
    return (
      <section className="manager-history" aria-labelledby="record-title">
        <h2 id="record-title">Your record</h2>
        <p role="status">
          FPL answered, but not in the shape I expect, so I am showing you
          nothing rather than guessing at your record. This one is mine to fix.
        </p>
      </section>
    );
  }

  if (loaded.profile === null) {
    return (
      <section className="manager-history" aria-labelledby="record-title">
        <h2 id="record-title">Your record</h2>
        <p role="status">
          FPL has no completed season on record for this team, so there is
          nothing for me to read. That is not a judgement — everyone starts
          somewhere.
        </p>
      </section>
    );
  }

  const profile = loaded.profile;
  const counts = countsOf(profile.seasons);

  return (
    <section className="manager-history" aria-labelledby="record-title">
      <div className="dossier-heading dossier-heading-compact">
        <div>
          <p className="eyebrow">On the record</p>
          <h2 id="record-title">Your record</h2>
        </div>
        <span className="archetype-badge mono">
          {ARCHETYPE_LABELS[profile.archetype]}
        </span>
      </div>

      <p className="andres-read">{commentary(profile)}</p>

      <dl className="record-summary">
        <div>
          <dt>Seasons</dt>
          <dd className="mono">{profile.seasonsPlayed}</dd>
        </div>
        <div>
          <dt>Best finish</dt>
          <dd className="mono">
            {profile.bestPercentile === null
              ? profile.bestRank.toLocaleString("en-GB")
              : `top ${share(profile.bestPercentile)}`}
            <span className="record-when"> in {profile.bestSeason}</span>
          </dd>
        </div>
        <div>
          <dt>Typical</dt>
          <dd className="mono">
            {profile.medianPercentile === null
              ? profile.medianRank.toLocaleString("en-GB")
              : `top ${share(profile.medianPercentile)}`}
          </dd>
        </div>
        <div>
          <dt>Top 1% seasons</dt>
          <dd className="mono">
            {counts.elite}{" "}
            <span className="record-when">of {counts.rated}</span>
          </dd>
        </div>
        <div>
          <dt>Top 10% seasons</dt>
          <dd className="mono">
            {counts.strong}{" "}
            <span className="record-when">of {counts.rated}</span>
          </dd>
        </div>
        <div>
          <dt>Spread</dt>
          <dd className="mono">
            {counts.spread === null ? "—" : `${counts.spread.toFixed(0)}pt`}
            <span className="record-when">
              {" "}
              {counts.spread === null
                ? ""
                : counts.spread < 15
                  ? "steady"
                  : counts.spread < 30
                    ? "variable"
                    : "swings hard"}
            </span>
          </dd>
        </div>
      </dl>

      <div className="record-chart">
        {/* The stated target, drawn rather than described: everything above the
            line is a top-one-percent season. */}
        <span
          aria-hidden="true"
          className="record-goal"
          style={{ bottom: "99%" }}
        >
          <span className="mono">top 1%</span>
        </span>
        <span
          aria-hidden="true"
          className="record-goal record-goal-soft"
          style={{ bottom: "90%" }}
        >
          <span className="mono">top 10%</span>
        </span>

        <ol className="record-seasons" aria-label="Season by season finishes">
          {profile.seasons.map((season) => {
            const finish =
              season.percentile === null
                ? rankBar(season.rank, profile.worstRank) * 100
                : 100 - season.percentile;
            const label =
              season.percentile === null
                ? `rank ${season.rank.toLocaleString("en-GB")}`
                : `top ${share(season.percentile)}`;
            const detail = [
              season.season,
              label,
              `rank ${season.rank.toLocaleString("en-GB")}`,
              `${String(season.points)} points`,
            ].join(" · ");
            return (
              <li key={season.season} title={detail}>
                <span className="record-column">
                  <span
                    aria-hidden="true"
                    className={`record-column-fill ${bandOf(season.percentile)}`}
                    style={{ height: `${Math.max(2, finish).toFixed(1)}%` }}
                  />
                </span>
                <span className="mono record-season-name">
                  {season.season.slice(2)}
                </span>
                <span className="visually-hidden">{detail}</span>
              </li>
            );
          })}
        </ol>
      </div>

      <ul className="record-key mono" aria-label="What the colours mean">
        <li>
          <span className="record-swatch is-elite" aria-hidden="true" />
          top 1%
        </li>
        <li>
          <span className="record-swatch is-strong" aria-hidden="true" />
          top 10%
        </li>
        <li>
          <span className="record-swatch is-fair" aria-hidden="true" />
          top 25%
        </li>
        <li>
          <span className="record-swatch is-weak" aria-hidden="true" />
          below
        </li>
      </ul>

      <p className="record-caveat">
        One bar per season, oldest first. Height is the share of the field you
        finished ahead of, so taller is better, and the colour is the same
        threshold the gridlines draw. Hover a bar for the finish, the rank and
        the points.
      </p>

      <p className="record-caveat">
        Total points is deliberately not plotted: it moves with the season, not
        with you — a year with more goals, more clean sheets or a new scoring
        route lifts everybody at once. Only the share compares across eras, and
        the field has grown roughly fivefold since 2010. The percentage is
        FPL&rsquo;s own.
      </p>
    </section>
  );
}
