import { useEffect, useState } from "react";

import {
  commentary,
  readManagerProfile,
  type ManagerProfile,
} from "../state/manager-profile";

type Loaded = { entryId: number; profile: ManagerProfile | null };

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

export function ManagerHistory({ entryId }: { entryId: number }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function read() {
      try {
        const response = await fetch(`/api/fpl/entry/${entryId}/history/`);
        const payload = response?.ok ? await response.json() : null;
        if (!cancelled) {
          setLoaded({ entryId, profile: readManagerProfile(payload) });
        }
      } catch {
        if (!cancelled) setLoaded({ entryId, profile: null });
      }
    }

    void read();
    return () => {
      cancelled = true;
    };
  }, [entryId]);

  // Derived rather than stored, so changing team never shows the old record.
  const ready = loaded !== null && loaded.entryId === entryId;

  if (!ready) {
    return (
      <section className="manager-history" aria-labelledby="record-title">
        <h2 id="record-title">Your record</h2>
        <p className="mono">Reading your history…</p>
      </section>
    );
  }

  if (loaded.profile === null) {
    return (
      <section className="manager-history" aria-labelledby="record-title">
        <h2 id="record-title">Your record</h2>
        <p>
          FPL has no completed season on record for this team, so there is
          nothing for me to read. That is not a judgement — everyone starts
          somewhere.
        </p>
      </section>
    );
  }

  const profile = loaded.profile;

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
      </dl>

      <ol className="record-seasons" aria-label="Season by season finishes">
        {profile.seasons.map((season) => (
          <li key={season.season}>
            <span className="mono record-season-name">{season.season}</span>
            <span
              className="record-bar"
              style={{
                width: `${
                  season.percentile === null
                    ? rankBar(season.rank, profile.worstRank) * 100
                    : Math.max(2, 100 - season.percentile)
                }%`,
              }}
              aria-hidden="true"
            />
            <span className="mono record-rank">
              {season.percentile === null
                ? season.rank.toLocaleString("en-GB")
                : `top ${share(season.percentile)}`}
            </span>
            <span className="mono record-points">{season.points} pts</span>
          </li>
        ))}
      </ol>

      <p className="record-caveat">
        Bars are the share of the field you finished ahead of, so a longer bar
        is a better season. Raw rank is not comparable across eras — the player
        base has grown roughly fivefold since 2010, so 100,000th today is a far
        better performance than 100,000th was then. The percentage is
        FPL&rsquo;s own.
      </p>
    </section>
  );
}
