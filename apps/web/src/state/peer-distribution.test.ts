import { describe, expect, it } from "vitest";

import { METRICS } from "./analysis-metrics";
import {
  analysisLinkFor,
  AXES_BY_POSITION,
  bandFor,
  FALLBACK_AXES,
  MINIMUM_PEERS,
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
      yellowCards: 0,
      redCards: 0,
      ownGoals: 0,
      penaltiesMissed: 0,
      defensiveContribution: 1,
    },
    evidence: "measured",
    ...over,
  };
}

const points = peerMetric("Points per match")!;

describe("who counts as a peer", () => {
  it("bands by the market's own tiers, not a flat step either side", () => {
    // A premium costs a different number in each position, and ±£0.5m is most
    // of the market at £4.5m and a sliver of it at £12.5m.
    expect(bandFor("MID", 125)).toEqual({ fromTenths: 75, toTenths: null });
    expect(bandFor("MID", 80)).toEqual({ fromTenths: 75, toTenths: null });
    expect(bandFor("FWD", 65)).toEqual({ fromTenths: 60, toTenths: 69 });
    expect(bandFor("DEF", 40)).toEqual({ fromTenths: 0, toTenths: 44 });
    expect(bandFor("GKP", 50)).toEqual({ fromTenths: 50, toTenths: null });
  });

  it("always puts the player inside his own band", () => {
    for (const position of ["GKP", "DEF", "MID", "FWD"]) {
      for (const price of [38, 45, 55, 70, 75, 125]) {
        const band = bandFor(position, price);
        expect(price).toBeGreaterThanOrEqual(band.fromTenths);
        if (band.toTenths !== null) {
          expect(price).toBeLessThanOrEqual(band.toTenths);
        }
      }
    }
  });

  it("finds players of the same position within the band", () => {
    const band = bandFor("DEF", 60);
    const found = peersOf("DEF", 60, points);
    for (const peer of found) {
      expect(peer.position).toBe("DEF");
      expect(peer.priceTenths ?? 0).toBeGreaterThanOrEqual(band.fromTenths);
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
  it("draws the dearest player rather than refusing him", () => {
    // The old rule returned null for anyone whose ±£0.5m band was thin, which
    // showed the reader nothing precisely for the players a transfer is
    // actually agonising over. The premium tier has no ceiling, so he lands
    // in it with every other premium in his position.
    expect(MINIMUM_PEERS).toBeGreaterThan(3);
    const spread = peerDistribution(projection({ priceTenths: 139 }), points);
    expect(spread).not.toBeNull();
    expect(spread!.fromTenths).toBeLessThanOrEqual(139);
    expect(spread!.peers).toBeGreaterThanOrEqual(MINIMUM_PEERS);
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
  const link = (over: Partial<PlayerProjection>) =>
    new URLSearchParams(analysisLinkFor(projection(over)).split("?")[1]);

  it("picks the route that decides each position", () => {
    const axis = (position: string) => link({ position }).get("x");

    expect(axis("DEF")).toBe("defconPer90");
    expect(axis("MID")).toBe("xGIPer90");
    expect(axis("FWD")).toBe("npxGPer90");
    // No saves metric exists, and a keeper's return turns on being first
    // choice, so minutes is the honest x for the position.
    expect(axis("GKP")).toBe("minutes");
  });

  it("never divides by a price the chart has already fixed", () => {
    // The band makes everyone on the chart cost about the same, so a
    // points-per-million axis would divide by a number they share.
    for (const position of ["GKP", "DEF", "MID", "FWD"]) {
      const params = link({ position });
      expect(params.get("x")).not.toBe("pointsPerMillion");
      expect(params.get("y")).not.toBe("pointsPerMillion");
    }
  });

  it("brackets the price a million either side", () => {
    const params = link({ priceTenths: 55 });
    expect(params.get("pricefrom")).toBe("45");
    expect(params.get("priceto")).toBe("65");
  });

  it("does not ask for a negative price", () => {
    expect(link({ priceTenths: 4 }).get("pricefrom")).toBe("0");
  });

  it("clears the filters that would hide the player it came from", () => {
    // The chart's browsing defaults are 1500 minutes and a 0.1 to 8 per cent
    // ownership band. A January signing fails the first and anyone the crowd
    // has found fails the second, so the link dropped the one player it exists
    // to show.
    const params = link({});
    expect(params.get("mins")).toBe("0");
    expect(params.get("from")).toBe("0");
    expect(params.get("to")).toBe("100");
  });

  it("marks the player it came from by code, not by club", () => {
    // A bare token is read as a club short name, so the chip rendered the raw
    // number and highlighted nobody.
    const params = link({ code: 4242 });
    expect(params.get("hl")).toBe("#4242");
    expect(params.get("pin")).toBe("4242");
    expect(params.get("pos")).toBe("DEF");
  });

  it("falls back rather than linking to an axis that does not exist", () => {
    expect(link({ position: "MNG" }).get("y")).toBe("xPts");
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
