import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { PinnedPlayers } from "../components/PinnedPlayers";
import { PlayerScatter } from "../components/PlayerScatter";
import { RouteHeading } from "../components/RouteHeading";
import { ScatterControls } from "../components/ScatterControls";
import { ScatterLegend } from "../components/ScatterLegend";
import { ScatterReadout } from "../components/ScatterReadout";
import { metric } from "../state/analysis-metrics";
import {
  fetchArchivedSeasons,
  type ArchivedSeason,
} from "../state/analysis-archive";
import { poolFromArchive } from "../state/analysis-archive-pool";
import {
  fetchAnalysisPool,
  type AnalysisData,
  type AnalysisFailure,
} from "../state/analysis-pool";
import { downloadBlob, scatterToPngBlob } from "../state/scatter-export";
import { readChart } from "../state/scatter-reading";
import { binsFor } from "../state/scatter-regions";
import { selectPlotted } from "../state/scatter-select";
import {
  readScatterView,
  writeScatterView,
  LIVE_SEASON,
  type ScatterView,
} from "../state/scatter-view";
import { useDocumentTitle } from "../state/use-document-title";

const MAX_PINNED = 4;

/**
 * The analysis page: every player in the game on two axes you choose.
 *
 * It opens on defensive contributions against expected involvement, because
 * that is the pairing the market has not caught up with. Two points a match for
 * defensive work was 7.5% of everything FPL paid out last season -- more than
 * assists -- and the players who did it best are still priced as squad filler.
 */
export default function AnalysisPage() {
  useDocumentTitle(
    "Analysis",
    "Every Fantasy Premier League player on two axes you choose, measured on last season.",
  );

  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<AnalysisData | null>(null);
  const [archive, setArchive] = useState<ArchivedSeason[] | null>(null);
  const [archiveFailed, setArchiveFailed] = useState(false);
  const [failed, setFailed] = useState<AnalysisFailure | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  const view = useMemo(() => readScatterView(searchParams), [searchParams]);

  const update = useCallback(
    (next: Partial<ScatterView>) => {
      const merged = { ...view, ...next };
      setSearchParams(writeScatterView(merged), { replace: true });
    },
    [view, setSearchParams],
  );

  const reset = useCallback(() => {
    setSearchParams("", { replace: true });
  }, [setSearchParams]);

  useEffect(() => {
    const controller = new AbortController();
    fetchAnalysisPool(fetch, controller.signal)
      .then(setData)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setFailed(
          error instanceof Error && "reason" in error
            ? (error.reason as AnalysisFailure)
            : "unreachable",
        );
      });
    return () => controller.abort();
  }, []);

  // A megabyte and a half, so it is fetched the first time a reader asks for a
  // past season and never on first paint.
  useEffect(() => {
    if (view.season === LIVE_SEASON || archive || archiveFailed) return;
    const controller = new AbortController();
    fetchArchivedSeasons(fetch, controller.signal)
      .then(setArchive)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setArchiveFailed(true);
      });
    return () => controller.abort();
  }, [view.season, archive, archiveFailed]);

  const shown = useMemo(() => {
    if (!data) return null;
    if (view.season === LIVE_SEASON) return data;
    const season = archive?.find((entry) => entry.season === view.season);
    if (!season) return null;
    const teamCodes = new Map(
      data.pool.players.map((player) => [player.club, player.teamCode]),
    );
    return {
      ...data,
      pool: poolFromArchive(season, view.fromEvent, view.toEvent, teamCodes),
    };
  }, [data, archive, view.season, view.fromEvent, view.toEvent]);

  const selection = useMemo(
    () => (shown ? selectPlotted(shown.pool.players, view) : null),
    [shown, view],
  );

  // A pin on a player the filters have since removed is a row in the comparison
  // for a mark that is not on the chart, which reads as a bug.
  useEffect(() => {
    if (!selection || view.pinned.length === 0) return;
    const plotted = new Set(selection.points.map((point) => point.player.code));
    const kept = view.pinned.filter((code) => plotted.has(code));
    if (kept.length !== view.pinned.length) update({ pinned: kept });
  }, [selection, view.pinned, update]);

  const togglePin = useCallback(
    (code: number) => {
      const already = view.pinned.includes(code);
      update({
        pinned: already
          ? view.pinned.filter((entry) => entry !== code)
          : [...view.pinned, code].slice(-MAX_PINNED),
      });
    },
    [view.pinned, update],
  );

  return (
    <section className="text-page analysis-page">
      <p className="eyebrow">Football analytics</p>
      <RouteHeading>Find the best player, statistically speaking.</RouteHeading>

      {failed ? (
        <p className="analysis-failure" role="status">
          {failed === "unreachable"
            ? "I could not reach FPL for the player list. Nothing here is worth showing without it."
            : "FPL sent back a player list I do not recognise, so I am not plotting it."}
        </p>
      ) : null}

      {archiveFailed ? (
        <p className="analysis-failure" role="status">
          I could not download the past-season archive, so I am staying on this
          season rather than plotting an empty chart.
        </p>
      ) : null}

      {shown && selection ? (
        <AnalysisBody
          data={shown}
          view={view}
          selection={selection}
          onChange={update}
          onReset={reset}
          onTogglePin={togglePin}
          chartRef={chartRef}
        />
      ) : failed ? null : (
        <p className="analysis-loading" role="status">
          {view.season === LIVE_SEASON
            ? "Pulling the player list."
            : `Downloading ${view.season}.`}
        </p>
      )}
    </section>
  );
}

function AnalysisBody({
  data,
  view,
  selection,
  onChange,
  onReset,
  onTogglePin,
  chartRef,
}: {
  data: AnalysisData;
  view: ScatterView;
  selection: NonNullable<ReturnType<typeof selectPlotted>>;
  onChange: (next: Partial<ScatterView>) => void;
  onReset: () => void;
  onTogglePin: (code: number) => void;
  chartRef: React.RefObject<HTMLDivElement | null>;
}) {
  const { vintage } = data.pool;

  if (vintage.state === "unavailable") {
    return (
      <p className="analysis-unavailable" role="status">
        FPL has cleared last season&rsquo;s totals and this season has not been
        scored yet, so there is nothing measured to plot. It comes back the
        moment a gameweek finishes. All forecasts are wrong. Some are useful;
        this one would not be.
      </p>
    );
  }

  const excluded = selection.excluded;

  const reading = readChart(selection, view);
  const clubsInPlay = [
    ...new Set(selection.points.map((point) => point.player.club)),
  ];
  // The legend has to bin exactly what the chart binned, so both read it here.
  const colourMetric =
    view.colourBy === "metric" ? (metric(view.colourMetric) ?? null) : null;
  const colourBins = colourMetric
    ? binsFor(
        selection.points.map((point) => point.player),
        colourMetric,
        view.bins,
      )
    : [];
  const sizeValues = selection.points
    .map((point) => point.size)
    .filter((value): value is number => value !== null);
  const sizeRange =
    sizeValues.length === 0
      ? null
      : { low: Math.min(...sizeValues), high: Math.max(...sizeValues) };

  return (
    <>
      {view.season === LIVE_SEASON ? (
        <p className="analysis-vintage">
          Plotting the <strong>{vintage.season}</strong> record
          {vintage.state === "previous_season"
            ? ", the last completed season"
            : `, ${vintage.completedGameweeks} gameweeks in`}
          . Price and ownership are today&rsquo;s. Shot quality is Understat,
          joined to {(data.pool.understatCoverage * 100).toFixed(0)}% of the
          pool.
        </p>
      ) : (
        <p className="analysis-vintage">
          Plotting <strong>{view.season}</strong>, gameweeks {view.fromEvent} to{" "}
          {view.toEvent}. Price is what he closed the window at, not what he
          costs now. Ownership was never recorded for a past season and shot
          quality is not in the archive, so both are blank
          {view.season < "2025-26"
            ? ", and defensive contributions did not exist yet"
            : ""}
          .
        </p>
      )}

      <div className="analysis-layout">
        <ScatterControls
          pool={data.pool}
          view={view}
          onChange={onChange}
          onReset={onReset}
          plotted={selection.points.length}
        />

        <div className="analysis-chart" ref={chartRef}>
          <details className="scatter-controls analysis-reading">
            <summary className="scatter-controls-summary">
              <span>How to read this</span>
            </summary>
            <div className="scatter-controls-body">
              <p>{reading.corner}</p>
              {reading.relationship ? <p>{reading.relationship}</p> : null}
              {reading.standout ? <p>{reading.standout}</p> : null}
              {reading.size ? <p>{reading.size}</p> : null}
            </div>
          </details>

          <PlayerScatter
            selection={selection}
            view={view}
            pinned={view.pinned}
            onTogglePin={onTogglePin}
          />

          <ScatterLegend
            bins={colourBins}
            clubsInPlay={clubsInPlay}
            colourMetric={colourMetric}
            sizeMetric={selection.size}
            sizeRange={sizeRange}
            view={view}
          />

          <div className="analysis-actions">
            <ExportButton chartRef={chartRef} view={view} />
          </div>

          <p className="analysis-excluded">
            {excluded.minutes} under the minutes threshold
            {excluded.noValue > 0
              ? `, ${excluded.noValue} with no reading on these axes`
              : ""}
            {excluded.position + excluded.club > 0
              ? `, ${excluded.position + excluded.club} filtered out`
              : ""}
            .
            {selection.unmeasured.length > 0 ? (
              <span className="analysis-unmeasured">
                {" "}
                No reading for {selection.unmeasured.slice(0, 4).join(", ")}
                {selection.unmeasured.length > 4 ? " and others" : ""}.
              </span>
            ) : null}
          </p>

          {selection.fit ? (
            <p className="analysis-fit">
              The line explains {(selection.fit.r2 * 100).toFixed(0)}% of the
              spread. Above it means he returned more than the pack does at his{" "}
              {selection.x.label}.
            </p>
          ) : null}
        </div>

        <PinnedPlayers
          players={data.pool.players}
          pinned={view.pinned}
          clubCodeByTeamId={data.clubCodeByTeamId}
          fixtures={data.fixtures}
          onUnpin={onTogglePin}
          onClear={() => onChange({ pinned: [] })}
          view={view}
        />
      </div>

      <ScatterReadout
        selection={selection}
        pinned={view.pinned}
        onTogglePin={onTogglePin}
        rankBy={view.tableMetric}
        onRankBy={(tableMetric) => onChange({ tableMetric })}
      />
    </>
  );
}

/**
 * The chart as a PNG.
 *
 * Deliberately a button rather than an automatic screenshot: rasterising five
 * hundred paths is not free, and nobody wants it happening on every filter
 * change.
 */
function ExportButton({
  chartRef,
  view,
}: {
  chartRef: React.RefObject<HTMLDivElement | null>;
  view: ScatterView;
}) {
  const [failed, setFailed] = useState(false);

  const save = async () => {
    const svg = chartRef.current?.querySelector("svg");
    if (!svg) return;
    try {
      setFailed(false);
      const blob = await scatterToPngBlob(svg);
      downloadBlob(blob, `fpl-andres-${view.x}-vs-${view.y}.png`);
    } catch {
      setFailed(true);
    }
  };

  return (
    <>
      <button type="button" className="analysis-export" onClick={save}>
        Save as PNG
      </button>
      {failed ? (
        <span role="status" className="analysis-export-failed">
          That did not rasterise. The view is still in the address bar.
        </span>
      ) : null}
    </>
  );
}
