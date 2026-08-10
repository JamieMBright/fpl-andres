/**
 * Where a player sits among the players you would actually buy instead of him.
 *
 * A number on the card is coloured against everyone in the position, which
 * answers "is this good for a defender" and not "is this good for a defender I
 * can afford". Those are different questions and only the second one decides a
 * transfer: nobody chooses between a £4.0m bench filler and a £6.5m starter.
 *
 * So the peer group is the position at roughly the same price. A flat ±£0.5m
 * was the wrong shape: it is most of the premium market at £4.5m and a sliver
 * of it at £12.5m, and it kept putting a £12.5m midfielder in a band that did
 * not contain the only players anyone would consider instead of him.
 *
 * The bands are the market's own tiers instead, per position, because a
 * "premium" costs a different number in each one. Everyone above the premium
 * threshold is compared with every other premium in that position, which is
 * what a manager is actually choosing between.
 *
 * Everything here reads the published projection artifact. No player is
 * imputed: a promoted-club debutant has no record, and a peer group padded with
 * assumed averages would report a percentile that means nothing.
 */

import type { PlayerProjection } from "./squad-projection";
import { allProjections } from "./squad-projection";
import { DEFAULT_HORIZON, horizonPoints } from "./horizon-points";
import { OWNERSHIP_CAP } from "./scatter-view";

/**
 * Where one tier ends and the next begins, per position, in FPL's tenths.
 *
 * The top figure is the premium threshold: £5.0m for a keeper, £5.5m for a
 * defender, £7.0m for a forward, £7.5m for a midfielder. Above it there is no
 * upper edge, so the £12.5m midfielder and the £8.0m one are in one band —
 * they are competing for the same squad slot and the same money.
 */
const TIER_EDGES: Record<string, readonly number[]> = {
  GKP: [45, 50],
  DEF: [45, 55],
  MID: [55, 75],
  FWD: [60, 70],
};

/** Used where a position has no declared tiers, so the band is still bounded. */
export const PEER_BAND_TENTHS = 5;

/**
 * Half a million, in FPL's tenths.
 *
 * A band edge of £6.3m is arithmetic showing through: nobody shops in tenths,
 * and a comparison that starts three-tenths above a round number silently drops
 * the players just below it. Edges are widened to the nearest half million so
 * the set is the one a manager would have drawn by hand.
 */
const PRICE_STEP_TENTHS = 5;

function floorToStep(tenths: number): number {
  return Math.max(
    0,
    Math.floor(tenths / PRICE_STEP_TENTHS) * PRICE_STEP_TENTHS,
  );
}

function ceilToStep(tenths: number): number {
  return Math.ceil(tenths / PRICE_STEP_TENTHS) * PRICE_STEP_TENTHS;
}

/** Fewer than this and a percentile is noise dressed as a measurement. */
export const MINIMUM_PEERS = 4;

export interface PeerBand {
  fromTenths: number;
  /** Null above the premium threshold, where the band has no ceiling. */
  toTenths: number | null;
}

/** The tier a price falls in. Always contains the price it was asked about. */
export function bandFor(position: string, priceTenths: number): PeerBand {
  const edges = TIER_EDGES[position];
  if (!edges) {
    return {
      fromTenths: floorToStep(priceTenths - PEER_BAND_TENTHS),
      toTenths: ceilToStep(priceTenths + PEER_BAND_TENTHS),
    };
  }
  let from = 0;
  for (const edge of edges) {
    if (priceTenths < edge) return { fromTenths: from, toTenths: edge - 1 };
    from = edge;
  }
  return { fromTenths: from, toTenths: null };
}

export interface PeerMetric {
  /** Matches the row term on the card. */
  term: string;
  value: (record: PlayerProjection) => number | null;
  format: (value: number) => string;
  higherIsBetter: boolean;
  /**
   * Compare against the whole position rather than the price tier.
   *
   * Only for metrics that already have price in them. Value per pound inside a
   * price band is very nearly a constant, so a tier comparison would report the
   * band edges rather than a finding; across the position it is the question
   * being asked.
   */
  acrossPosition?: boolean;
  /** The chart to open for this row, where the position's own pair is wrong. */
  axes?: { x: string; y: string };
}

const two = (value: number) => value.toFixed(2);
const one = (value: number) => value.toFixed(1);
const whole = (value: number) => String(Math.round(value));
const rate = (value: number) => `${Math.round(value * 100)}%`;

/**
 * Every card row that has a distribution worth looking at.
 *
 * "Per £1m" is deliberately absent: price is what defines the peer group, so
 * within a band it is very nearly the same number for everyone and the spread
 * would be an artefact of the band edges rather than a finding.
 */
export const PEER_METRICS: readonly PeerMetric[] = [
  {
    term: "Points per match",
    value: (record) => record.expectedPoints,
    format: two,
    higherIsBetter: true,
  },
  {
    term: `xPts${String(DEFAULT_HORIZON)}`,
    value: (record) => horizonPoints(record.code, DEFAULT_HORIZON),
    format: one,
    higherIsBetter: true,
    // Against the run, not against the price: the whole point of the horizon is
    // that two players on the same money have different fixtures.
    axes: { x: "xPts", y: `xPts${String(DEFAULT_HORIZON)}` },
  },
  {
    term: "Per \u00a31m",
    value: (record) =>
      record.priceTenths === null || record.priceTenths <= 0
        ? null
        : record.expectedPoints / (record.priceTenths / 10),
    format: two,
    higherIsBetter: true,
    acrossPosition: true,
    axes: { x: "price", y: "xPts" },
  },
  {
    term: "Minutes",
    value: (record) => record.expectedMinutes,
    format: whole,
    higherIsBetter: true,
  },
  {
    term: "Starts",
    value: (record) => record.probabilityStart,
    format: rate,
    higherIsBetter: true,
  },
  {
    term: "Appears",
    value: (record) => record.probabilityAppear,
    format: rate,
    higherIsBetter: true,
  },
  {
    term: "Appearances",
    value: (record) => record.appearances,
    format: whole,
    higherIsBetter: true,
  },
  {
    term: "Returned",
    value: (record) => record.returnRate,
    format: rate,
    higherIsBetter: true,
  },
  {
    term: "Blanked",
    value: (record) => record.blankRate,
    format: rate,
    higherIsBetter: false,
  },
  {
    term: "Floor",
    value: (record) => record.floor,
    format: whole,
    higherIsBetter: true,
  },
  {
    term: "Median",
    value: (record) => record.median,
    format: whole,
    higherIsBetter: true,
  },
  {
    term: "Ceiling",
    value: (record) => record.ceiling,
    format: whole,
    higherIsBetter: true,
  },
  {
    term: "Yellow cards",
    value: (record) => record.yellowCards,
    format: whole,
    higherIsBetter: false,
  },
  {
    term: "Suspension derate",
    value: (record) => record.suspensionMultiplier,
    format: two,
    higherIsBetter: true,
  },
];

export function peerMetric(term: string): PeerMetric | null {
  return PEER_METRICS.find((metric) => metric.term === term) ?? null;
}

export interface PeerBin {
  from: number;
  to: number;
  count: number;
  /** True for the bin the subject falls in. */
  holdsSubject: boolean;
}

export interface PeerDistribution {
  position: string;
  fromTenths: number;
  toTenths: number;
  /** True where the tier was too thin and the whole position was used. */
  widened: boolean;
  /** Everyone in the band with a value for this metric, the subject included. */
  peers: number;
  subject: number;
  bins: PeerBin[];
  /** Share of peers the subject is better than, on this metric's own direction. */
  percentile: number;
  best: { name: string; value: number };
  worst: { name: string; value: number };
  median: number;
}

/** Same position, inside the same market tier, carrying a record. */
export function peersOf(
  position: string,
  priceTenths: number,
  metric: PeerMetric,
): PlayerProjection[] {
  if (metric.acrossPosition) return wholePosition(position, metric);
  const band = bandFor(position, priceTenths);
  return allProjections().filter(
    (candidate) =>
      candidate.position === position &&
      candidate.priceTenths !== null &&
      candidate.priceTenths >= band.fromTenths &&
      (band.toTenths === null || candidate.priceTenths <= band.toTenths) &&
      metric.value(candidate) !== null,
  );
}

/** Everyone in the position with a record, when the tier is too thin to read. */
function wholePosition(
  position: string,
  metric: PeerMetric,
): PlayerProjection[] {
  return allProjections().filter(
    (candidate) =>
      candidate.position === position && metric.value(candidate) !== null,
  );
}

export function peerDistribution(
  subject: PlayerProjection,
  metric: PeerMetric,
  binCount = 8,
): PeerDistribution | null {
  const price = subject.priceTenths;
  const own = metric.value(subject);
  if (price === null || own === null) return null;

  const band = bandFor(subject.position, price);
  const tier = peersOf(subject.position, price, metric);
  // The subject is never allowed to fall out of his own chart. Where his tier
  // is too thin to describe, the comparison widens to the whole position
  // rather than refusing to draw: a wider answer beats no answer.
  const widened = tier.length < MINIMUM_PEERS;
  const group = widened ? wholePosition(subject.position, metric) : tier;
  // The subject has to be inside his own population or the percentile divides
  // by the wrong count and can come out above one.
  const population = group.some((peer) => peer.code === subject.code)
    ? group
    : [...group, subject];
  if (population.length < MINIMUM_PEERS) return null;

  const values = population
    .map((peer) => ({ peer, value: metric.value(peer) ?? 0 }))
    .sort((left, right) => left.value - right.value);
  const low = values[0]?.value ?? 0;
  const high = values[values.length - 1]?.value ?? 0;

  // A band where everyone scores the same has no distribution to draw.
  const span = high - low;
  const width = span === 0 ? 1 : span / binCount;
  const bins: PeerBin[] = Array.from({ length: binCount }, (_, index) => ({
    from: low + index * width,
    to: low + (index + 1) * width,
    count: 0,
    holdsSubject: false,
  }));
  const binOf = (value: number) =>
    Math.min(binCount - 1, Math.max(0, Math.floor((value - low) / width)));
  for (const { value } of values) bins[binOf(value)]!.count += 1;
  bins[binOf(own)]!.holdsSubject = true;

  const beaten = values.filter(({ value }) =>
    metric.higherIsBetter ? value < own : value > own,
  ).length;
  const middle = values[Math.floor(values.length / 2)]?.value ?? own;

  const ranked = metric.higherIsBetter ? [...values].reverse() : values;
  const priced = population
    .map((peer) => peer.priceTenths)
    .filter((value): value is number => value !== null);
  return {
    position: subject.position,
    fromTenths: widened ? Math.min(...priced) : band.fromTenths,
    toTenths: widened
      ? Math.max(...priced)
      : (band.toTenths ?? Math.max(...priced)),
    widened,
    peers: values.length,
    subject: own,
    bins,
    percentile: beaten / Math.max(1, values.length - 1),
    best: { name: ranked[0]!.peer.name, value: ranked[0]!.value },
    worst: {
      name: ranked[ranked.length - 1]!.peer.name,
      value: ranked[ranked.length - 1]!.value,
    },
    median: middle,
  };
}

/**
 * The chart worth opening for this position, as an analysis-page URL.
 *
 * The axes differ by position because the route that decides a player differs:
 * a defender is bought for clean sheets and defensive contribution, a
 * midfielder for goal involvement, a forward for shot volume and quality, a
 * keeper for saves he is actually called on to make. Plotting all four against
 * the same pair would flatter whichever position the axes happened to suit.
 *
 * Size is expected minutes throughout — a big dot is a player who plays — and
 * colour is the club, so a cluster from one team is visible as one.
 */
/**
 * Ids from `analysis-metrics`, not imported from it: that module pulls in the
 * whole analysis pool, and the player card would carry it for four strings.
 * `peer-distribution.test.ts` fails if any of these stops being a real metric.
 *
 * Neither axis is points-per-million. The chart is already filtered to a price
 * bracket, so everyone on it costs about the same and dividing by a number they
 * share only adds noise. Inside a bracket the question is who is better, not
 * who is cheaper.
 */
export const AXES_BY_POSITION: Readonly<
  Record<string, { x: string; y: string }>
> = {
  // No saves metric exists, and a keeper's return is dominated by whether he
  // is first choice, so minutes is the honest x for the position.
  GKP: { x: "minutes", y: "xPts" },
  DEF: { x: "defconPer90", y: "xPts" },
  MID: { x: "xGIPer90", y: "xPts" },
  FWD: { x: "npxGPer90", y: "xPts" },
};

export const FALLBACK_AXES = { x: "minutes", y: "xPts" };

/** One million either side, which is two FPL price steps. */
export const LINK_BAND_TENTHS = 10;

/**
 * A link that is guaranteed to plot the player it came from.
 *
 * The chart's own defaults exist for browsing: 1500 minutes and a 0.1 to 8 per
 * cent ownership band, which together drop a January signing and anyone the
 * crowd has found. Both quietly removed the player the reader had just clicked
 * on, which is the one thing this link exists to show. So it clears them and
 * narrows on price instead, which is the filter that makes the remaining
 * players genuine alternatives.
 */
export function analysisLinkFor(
  subject: PlayerProjection,
  metric?: PeerMetric,
): string {
  const axes =
    metric?.axes ?? AXES_BY_POSITION[subject.position] ?? FALLBACK_AXES;
  // `#code` is a player; a bare token is read as a club short name.
  const token = `#${String(subject.code)}`;
  const params = new URLSearchParams({
    x: axes.x,
    y: axes.y,
    size: "price",
    colour: "club",
    pos: subject.position,
    // The band is a dozen players, so names fit and the good-value shading
    // reads. The frontier answers "who is undominated here", which is the
    // question a peer group asks; a median trend line only restates the middle.
    names: "1",
    ring: "1",
    front: "1",
    mins: "0",
    from: "0",
    to: String(OWNERSHIP_CAP),
    hl: token,
    pin: String(subject.code),
  });
  // A metric with price already in it is asked across the whole position, so
  // narrowing to a price band would remove every player it exists to compare.
  if (subject.priceTenths !== null && !metric?.acrossPosition) {
    params.set(
      "pricefrom",
      String(floorToStep(subject.priceTenths - LINK_BAND_TENTHS)),
    );
    params.set(
      "priceto",
      String(ceilToStep(subject.priceTenths + LINK_BAND_TENTHS)),
    );
  }
  return `/analysis?${params.toString()}`;
}
