import { Link } from "react-router-dom";

import artifact from "../data/fpl500.json";
import { fineShare, oneDecimal } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";

export function Fpl500Teaser() {
  const sample = artifact.exactFpl500Portfolio.samples["01"];
  const aggregate = sample?.aggregate;
  if (!sample || !aggregate) return null;
  const holdings = artifact.exactFpl500Portfolio.holdings?.["01"] ?? [];
  const topOwned = [...holdings].sort(
    (left, right) => right.ownedShare - left.ownedShare,
  )[0];
  const topCaptain = artifact.exactFpl500Portfolio.captains?.["01"]?.[0];
  const playerName = (elementId: number | undefined) =>
    elementId === undefined
      ? "—"
      : (PLAYERS_BY_ELEMENT_ID.get(elementId)?.name ??
        `Element ${String(elementId)}`);
  const chipCount = sample.responded - (aggregate.chips.none ?? 0);
  const chipShare = sample.responded > 0 ? chipCount / sample.responded : 0;
  return (
    <Link className="fpl500-teaser" to="/fpl500">
      <strong>FPL500 · GW1</strong>
      <span>
        <small>Exact sample</small>
        <b>{sample.responded}</b>
      </span>
      <span>
        <small>Mean</small>
        <b>{oneDecimal.format(aggregate.totalPoints.mean)}</b>
      </span>
      <span>
        <small>Median</small>
        <b>{oneDecimal.format(aggregate.totalPoints.median)}</b>
      </span>
      <span>
        <small>Used a chip</small>
        <b>{fineShare.format(chipShare)}</b>
      </span>
      <span>
        <small>Top owned</small>
        <b>{playerName(topOwned?.elementId)}</b>
        <em>{topOwned ? fineShare.format(topOwned.ownedShare) : "—"}</em>
      </span>
      <span>
        <small>Top captain</small>
        <b>{playerName(topCaptain?.elementId)}</b>
        <em>{topCaptain ? fineShare.format(topCaptain.share) : "—"}</em>
      </span>
    </Link>
  );
}
