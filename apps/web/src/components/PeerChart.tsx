import { useEffect, useMemo, useState } from "react";

import { PlayerScatter } from "./PlayerScatter";
import { fetchAnalysisPool, type AnalysisData } from "../state/analysis-pool";
import { selectPlotted } from "../state/scatter-select";
import { readScatterView } from "../state/scatter-view";

/**
 * The peer chart, drawn where the reader already is.
 *
 * The card used to link out to the analysis page. That is a worse answer than
 * it looks: following it abandons whatever the reader had set up, and the
 * question — "where does this player sit among the ones he competes with" — is
 * a glance, not a destination. The link already carried a complete chart
 * configuration, so the same configuration is read here and drawn in place.
 */
export function PeerChart({ link }: { link: string }) {
  const [pool, setPool] = useState<AnalysisData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchAnalysisPool(fetch, controller.signal)
      .then(setPool)
      .catch(() => {
        // An aborted fetch is the modal closing, not a failure to report.
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
    };
  }, []);

  // The link is the single source of truth for what the chart shows, so the
  // inline copy and the full page cannot drift apart.
  const view = useMemo(
    () => readScatterView(new URLSearchParams(link.split("?")[1] ?? "")),
    [link],
  );

  const selection = useMemo(
    () => (pool ? selectPlotted(pool.pool.players, view) : null),
    [pool, view],
  );

  if (failed) {
    return (
      <p className="peer-chart-state" role="status">
        FPL is not answering, so the chart is not drawn. Nothing has been
        substituted for it.
      </p>
    );
  }

  if (!selection) {
    return (
      <p className="peer-chart-state" role="status">
        Reading the player list from FPL…
      </p>
    );
  }

  return (
    <div className="peer-chart">
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={view.pinned}
        onTogglePin={() => {
          // Pinning belongs to the analysis page, which owns the URL. Here the
          // chart is a read-only illustration of one player's peer group.
        }}
        onOverlays={() => {
          // The readout that consumes overlay notes lives on the analysis page.
        }}
      />
    </div>
  );
}
