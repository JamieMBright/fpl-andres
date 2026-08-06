import { describe, expect, it } from "vitest";

import { METRICS } from "./analysis-metrics";
import {
  analysisLinkFor,
  AXES_BY_POSITION,
  FALLBACK_AXES,
  MINIMUM_PEERS,
  PEER_BAND_TENTHS,
  PEER_METRICS,
  peerDistribution,
  peerMetric,
  peersOf,
} from "./peer-distribution";
import type { PlayerProjection } from "./squad-projection";

/**
 * The card colours a figure against the whole position. This asks the question
 * a transfer actually asks: against the players at the same price.
 */

function projection(over: Partial<PlayerProjection>): PlayerProjection {
  return {
    code: 1,
    name: "Player",
    position: "DEF",
    priceTenths: 60,
    expectedPoints: 4,
    expectedCeiling: 8,
    ceilingRatio: 2,
    expectedMinutes: 80,
    probabilityAppear: 0.9,
    probabilityStart: 0.85,
    appearances: 30,
    floor: 2,
    median: 4,
    ceiling: 10,
    returnRate: 0.3,
    blankRate: 0.4,
    yellowCards: 4,
    suspensionMultiplier: 0.97,
    routes: {
      appearance: 1,
      attacking: 1,
      cleanSheet: 1,
      bonus: 0,
      saves: 0,
      conceding: 0,
      discipline: 0,
      defensiveContribution: 1,
    },
    evidence: "measured",
    ...over,
  };
}

const points = peerMetric("Points per match")!;

describe("who counts as a peer", () => {
  it("keeps the price band symmetric and one step wide", () => {
    // A transfer chooses between players you can actually afford, so the band
    // is what defines the comparison rather than the whole position.
    expect(PEER_BAND_TENTHS).toBe(5);
  });

  it("finds players of the same position within the band", () => {
    const found = peersOf("DEF", 60, points);
    for (const peer of found) {
      expect(peer.position).toBe("DEF");
      expect(Math.abs((peer.priceTenths ?? 0) - 60)).toBeLessThanOrEqual(5);
    }
    expect(found.length).toBeGreaterThan(0);
  });

  it("does not mix positions", () => {
    expect(peersOf("GKP", 45, points).every((p) => p.position === "GKP")).toBe(
      true,
    );
  });
});

describe("the distribution", () => {
  it("refuses to report a percentile over too few players", () => {
    // A band with three players in it produces percentiles of 0, 50 and 100,
    // which look like measurements and are not.
    expect(MINIMUM_PEERS).toBeGreaterThan(3);
    expect(
      peerDistribution(projection({ priceTenths: 139 }), points),
    ).toBeNull();
  });

  it("says nothing for a player with no price", () => {
    expect(
      peerDistribution(projection({ priceTenths: null }), points),
    ).toBeNull();
  });

  it("marks exactly one bin as the subject's", () => {
    const spread = peerDistribution(projection({ priceTenths: 45 }), points);
    if (spread === null) return;
    expect(spread.bins.filter((bin) => bin.holdsSubject)).toHaveLength(1);
  });

  it("counts every peer exactly once across the bins", () => {
    const spread = peerDistribution(projection({ priceTenths: 45 }), points);
    if (spread === null) return;
    const counted = spread.bins.reduce((total, bin) => total + bin.count, 0);
    expect(counted).toBe(spread.peers);
  });

  it("reads a percentile in the metric's own direction", () => {
    // Blanking is the one where low is good. A rule that always treated high as
    // better would report the most reliable player in the band as the worst.
    const blanked = peerMetric("Blanked")!;
    expect(blanked.higherIsBetter).toBe(false);

    const good = peerDistribution(
      projection({ priceTenths: 45, blankRate: 0.01 }),
      blanked,
    );
    if (good === null) return;
    expect(good.percentile).toBeGreaterThan(0.9);
  });

  it("puts a runaway leader near the top", () => {
    const spread = peerDistribution(
      projection({ priceTenths: 45, expectedPoints: 99 }),
      points,
    );
    if (spread === null) return;
    expect(spread.percentile).toBe(1);
  });
});

describe("the metrics offered", () => {
  it("leaves out the one the band itself determines", () => {
    // Within a ±£0.5m band, points per £1m is very nearly points per match
    // rescaled by a constant, so its spread is an artefact of the band edges.
    expect(peerMetric("Per £1m")).toBeNull();
  });

  it("names only rows the card actually shows", () => {
    for (const metric of PEER_METRICS) {
      expect(metric.term.length).toBeGreaterThan(0);
      expect(peerMetric(metric.term)).toBe(metric);
    }
  });
});

describe("the chart it links to", () => {
  it("picks the route that decides each position", () => {
    const axis = (position: string) =>
      new URLSearchParams(
        analysisLinkFor(projection({ position })).split("?")[1],
      ).get("y");

    expect(axis("DEF")).toBe("defconPer90");
    expect(axis("MID")).toBe("xGIPer90");
    expect(axis("FWD")).toBe("npxGPer90");
    expect(axis("GKP")).toBe("xPts");
  });

  it("marks the player it came from", () => {
    const params = new URLSearchParams(
      analysisLinkFor(projection({ code: 4242 })).split("?")[1],
    );
    expect(params.get("hl")).toBe("4242");
    expect(params.get("pin")).toBe("4242");
    expect(params.get("pos")).toBe("DEF");
  });

  it("falls back rather than linking to an axis that does not exist", () => {
    const params = new URLSearchParams(
      analysisLinkFor(projection({ position: "MNG" })).split("?")[1],
    );
    expect(params.get("y")).toBe("xPts");
  });

  it("names only axes the analysis page actually offers", () => {
    // The ids are copied rather than imported, because importing the metric
    // registry would drag the whole analysis pool into the player card. This is
    // what keeps the copy honest.
    const ids = new Set(METRICS.map((metric) => metric.id));
    const used = [...Object.values(AXES_BY_POSITION), FALLBACK_AXES].flatMap(
      (axes) => [axes.x, axes.y],
    );

    expect(used.filter((id) => !ids.has(id))).toEqual([]);
    expect(ids.has("minutes")).toBe(true);
  });
});
