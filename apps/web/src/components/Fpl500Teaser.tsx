import { Link } from "react-router-dom";

import artifact from "../data/fpl500.json";
import { fineShare, oneDecimal } from "../format";

export function Fpl500Teaser() {
  const sample = artifact.exactFpl500Portfolio.samples["01"];
  const aggregate = sample?.aggregate;
  if (!sample || !aggregate) return null;
  return (
    <Link className="fpl500-teaser" to="/fpl500">
      <strong>FPL500 · GW1</strong>
      <span>
        <small>Mean</small>
        <b>{oneDecimal.format(aggregate.totalPoints.mean)}</b>
      </span>
      <span>
        <small>Median</small>
        <b>{oneDecimal.format(aggregate.totalPoints.median)}</b>
      </span>
      <span>
        <small>Bench Boost</small>
        <b>{fineShare.format(aggregate.chips.bboost / sample.responded)}</b>
      </span>
    </Link>
  );
}
