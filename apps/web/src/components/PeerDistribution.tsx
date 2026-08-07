import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";

import { PeerChart } from "./PeerChart";
import {
  analysisLinkFor,
  peerDistribution,
  type PeerMetric,
} from "../state/peer-distribution";
import { money as sharedMoney } from "../format";
import type { PlayerProjection } from "../state/squad-projection";
import { projectionSeason } from "../state/squad-projection";

function money(valueTenths: number): string {
  return `${sharedMoney.format(valueTenths / 10)}m`;
}

/**
 * One number on the card, put back among the players it competes with.
 *
 * The card already colours each figure against the whole position. That says
 * whether four points a match is good for a defender; it does not say whether
 * it is good for a defender at this price, which is the only version of the
 * question a transfer actually asks.
 */
export function PeerDistribution({
  subject,
  metric,
  onClose,
}: {
  subject: PlayerProjection;
  metric: PeerMetric;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
  }, []);

  const spread = peerDistribution(subject, metric);
  const link = useMemo(() => analysisLinkFor(subject), [subject]);

  return (
    <dialog
      aria-label={`${metric.term} among comparable players`}
      className="player-detail peer-spread"
      onClose={onClose}
      ref={dialog}
    >
      <div className="player-detail-inner">
        <button className="player-detail-close" onClick={onClose} type="button">
          Close
        </button>

        <h2>{metric.term}</h2>

        {spread === null ? (
          <p>
            Too few {subject.position}s within £0.5m of{" "}
            {subject.priceTenths === null
              ? "his price"
              : money(subject.priceTenths)}{" "}
            carry this figure, so there is no distribution to show. A percentile
            over three players is noise wearing a number.
          </p>
        ) : (
          <>
            <p className="peer-spread-band">
              {spread.peers} {subject.position}
              {spread.peers === 1 ? "" : "s"} priced {money(spread.fromTenths)}{" "}
              to {money(spread.toTenths)} at the close of {projectionSeason} —
              the players you would buy instead of him. The band is last
              season&rsquo;s price because that is the one every player in the
              record shares; today&rsquo;s price is on the card above.
            </p>

            <ol className="peer-spread-bars">
              {spread.bins.map((bin) => (
                <li
                  className={
                    bin.holdsSubject ? "peer-bin peer-bin-subject" : "peer-bin"
                  }
                  key={bin.from}
                >
                  <span
                    className="peer-bin-fill"
                    style={{
                      // Against the fullest bin, so a flat spread still reads.
                      inlineSize: `${String(
                        (bin.count /
                          Math.max(...spread.bins.map((each) => each.count))) *
                          100,
                      )}%`,
                    }}
                  />
                  <span className="peer-bin-label mono">
                    {metric.format(bin.from)}
                  </span>
                  <span className="peer-bin-count mono">{bin.count}</span>
                </li>
              ))}
            </ol>

            <p className="peer-spread-verdict">
              <strong>{subject.name}</strong> is on{" "}
              {metric.format(spread.subject)} against a middling{" "}
              {metric.format(spread.median)} for the band, which puts him ahead
              of {Math.round(spread.percentile * 100)}% of them.{" "}
              {spread.best.name} leads it on {metric.format(spread.best.value)}{" "}
              and {spread.worst.name} props it up on{" "}
              {metric.format(spread.worst.value)}.
            </p>
          </>
        )}

        <p className="peer-spread-more">
          <Link to={link}>
            Open this chart on the analysis page, where you can change it
          </Link>
        </p>

        <PeerChart link={link} />
      </div>
    </dialog>
  );
}
