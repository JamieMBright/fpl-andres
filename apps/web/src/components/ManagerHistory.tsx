import { useEffect, useState } from "react";

import { classifyFetchFailure } from "../state/fetch-failure";
import {
  commentary,
  readManagerProfile,
  type ManagerProfile,
} from "../state/manager-profile";

type Loaded = {
  entryId: number;
  profile: ManagerProfile | "unreadable" | null;
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
        const payload = response?.ok ? await response.json() : null;
        setLoaded({ entryId, profile: readManagerProfile(payload) });
      } catch (error) {
        if (classifyFetchFailure(error).kind === "aborted") {
          return;
        }
        setLoaded({ entryId, profile: null });
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
        {/* Audit item #135. Every other loading and empty state on the site is
            a status region; these two were plain paragraphs, so a screen
            reader was told nothing when the record arrived or turned out not
            to exist. */}
        <p className="mono" role="status">
          Reading your history…
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
            return (
              <li
                key={season.season}
                title={`${season.season} · ${label} · ${String(season.points)} pts`}
              >
                <span className="record-column">
                  <span
                    aria-hidden="true"
                    className={
                      season.percentile !== null && season.percentile <= 1
                        ? "record-column-fill is-elite"
                        : "record-column-fill"
                    }
                    style={{ height: `${Math.max(2, finish).toFixed(1)}%` }}
                  />
                </span>
                <span className="mono record-season-name">
                  {season.season.slice(2, 4)}
                </span>
                <span className="visually-hidden">
                  {season.season}: {label}
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      <p className="record-caveat">
        One bar per season, oldest first, labelled by its starting year. Height
        is the share of the field you finished ahead of, so taller is better and
        the two lines are the top ten percent and the top one percent. Hover a
        bar for the finish and the points.
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
