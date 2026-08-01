import cohort from "../data/cohort.json";

type Cohort = {
  generatedAt: string;
  rankCeiling: number;
  sinceSeasonStartYear: number;
  entriesSwept: number;
  sweepComplete: boolean;
  managers: number;
  qualifyingSeasonCounts: Record<string, number>;
  seasonsRepresented: Record<string, number>;
  bestRankMedian: number | null;
  persistenceMeasurable: boolean;
  persistenceNote: string;
};

const data = cohort as Cohort;
const number = new Intl.NumberFormat("en-GB");

/** The swept cohort, and the one thing it cannot tell you. */
export function CohortPanel() {
  const seasons = Object.entries(data.seasonsRepresented);
  const counts = Object.entries(data.qualifyingSeasonCounts);

  return (
    <section className="cohort-panel" aria-labelledby="cohort-title">
      <div className="dossier-heading dossier-heading-compact">
        <div>
          <p className="eyebrow">Who is actually good</p>
          <h2 id="cohort-title">The proven manager cohort</h2>
        </div>
        <span className="mono plan-state">
          {data.sweepComplete ? "Complete" : "Partial"}
        </span>
      </div>

      <p>
        I swept {number.format(data.entriesSwept)} entry ids and kept the{" "}
        {number.format(data.managers)} managers who finished inside the top{" "}
        {number.format(data.rankCeiling)} at least twice since{" "}
        {data.sinceSeasonStartYear}.
        {data.sweepComplete
          ? ""
          : " The sweep is still running, so these numbers will grow."}
      </p>

      {data.bestRankMedian === null ? null : (
        <p className="mono">
          Median best finish in the cohort: {number.format(data.bestRankMedian)}
        </p>
      )}

      <h3>How often they clear the bar</h3>
      <ul className="plan-promises">
        {counts.map(([qualifying, managers]) => (
          <li key={qualifying}>
            <span className="mono">{qualifying}</span> qualifying seasons —{" "}
            {number.format(managers)} managers
          </li>
        ))}
      </ul>

      <h3>Seasons represented</h3>
      <ul className="plan-promises">
        {seasons.map(([season, managers]) => (
          <li key={season}>
            <span className="mono">{season}</span> — {number.format(managers)}{" "}
            qualifying finishes
          </li>
        ))}
      </ul>

      {data.persistenceMeasurable ? null : (
        <div className="cohort-caveat">
          <h3>What this cannot tell you</h3>
          <p>{data.persistenceNote}</p>
        </div>
      )}
    </section>
  );
}
