import { Link } from "react-router-dom";

import artifact from "../data/fpl500.json";
import { fineShare, integer } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { transferFlow } from "../state/transfer-flow";
import { latestCapture, type Fpl500 } from "./Fpl500Playbook";

export function Fpl500Teaser() {
  const data = artifact as Fpl500;
  const series = data.exactFpl500Portfolio;
  const latest = latestCapture(series);
  if (!latest) return null;
  const sample = series.samples[latest.key];
  const aggregate = sample?.aggregate;
  if (!sample || !aggregate) return null;
  const ranks = (aggregate.seasonStanding ?? []).flatMap((row) =>
    row.overallRank === null ? [] : [row.overallRank],
  );
  const bestRank = ranks.length > 0 ? Math.min(...ranks) : null;
  const meanRank =
    ranks.length > 0
      ? Math.round(
          ranks.reduce((total, rank) => total + rank, 0) / ranks.length,
        )
      : null;
  const movement = transferFlow(
    {
      ...series,
      events: series.events.filter((event) => event <= latest.event),
    },
    1,
  );
  const mostTransferredIn = [...movement].sort(
    (left, right) =>
      right.transfersIn - left.transfersIn || right.net - left.net,
  )[0];
  const mostTransferredOut = [...movement].sort(
    (left, right) =>
      right.transfersOut - left.transfersOut || left.net - right.net,
  )[0];
  const transferredIn = mostTransferredIn?.transfersIn
    ? mostTransferredIn
    : undefined;
  const transferredOut = mostTransferredOut?.transfersOut
    ? mostTransferredOut
    : undefined;
  const topCaptain = series.captains?.[latest.key]?.[0];
  return (
    <Link className="fpl500-teaser" to="/fpl500">
      <strong>FPL500 · GW{latest.event}</strong>
      <span>
        <small>Exact sample</small>
        <b>{sample.responded}</b>
      </span>
      <span>
        <small>Best overall rank</small>
        <b>{bestRank === null ? "—" : integer.format(bestRank)}</b>
      </span>
      <span>
        <small>Mean overall rank</small>
        <b>{meanRank === null ? "—" : integer.format(meanRank)}</b>
      </span>
      <span>
        <small>Most transferred in</small>
        <b>{transferredIn?.name ?? "—"}</b>
        <em>
          {transferredIn
            ? `+${integer.format(transferredIn.transfersIn)}`
            : "—"}
        </em>
      </span>
      <span>
        <small>Most transferred out</small>
        <b>{transferredOut?.name ?? "—"}</b>
        <em>
          {transferredOut
            ? `-${integer.format(transferredOut.transfersOut)}`
            : "—"}
        </em>
      </span>
      <span>
        <small>Most captained</small>
        <b>
          {topCaptain === undefined
            ? "—"
            : (PLAYERS_BY_ELEMENT_ID.get(topCaptain.elementId)?.name ??
              `Element ${String(topCaptain.elementId)}`)}
        </b>
        <em>{topCaptain ? fineShare.format(topCaptain.share) : "—"}</em>
      </span>
    </Link>
  );
}
