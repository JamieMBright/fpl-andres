import { metric, type Metric } from "./analysis-metrics";
import type { AnalysisPlayer } from "./analysis-pool";
import {
  centre,
  leastSquaresFit,
  quadrantOf,
  residualOf,
  type Fit,
  type Point,
  type Quadrant,
} from "./scatter-stats";
import type { ScatterView } from "./scatter-view";

/**
 * Turning the pool and the current view into the points actually drawn.
 *
 * Every exclusion is counted and named. A chart that silently drops two hundred
 * players looks like a chart of the whole league, and the reader would have no
 * way to tell that the axis he picked is the reason his man is missing.
 */

export interface PlottedPlayer {
  player: AnalysisPlayer;
  x: number;
  y: number;
  size: number | null;
  quadrant: Quadrant;
  /** Distance above the trend line, when one is drawn. */
  residual: number | null;
  /** Strong quadrant, almost nobody owns him. */
  overlooked: boolean;
  /** Dimmed because a search is running and this is not the match. */
  matched: boolean;
}

export interface Exclusions {
  minutes: number;
  position: number;
  club: number;
  ownership: number;
  price: number;
  noValue: number;
}

export interface Selection {
  points: PlottedPlayer[];
  centres: Point | null;
  fit: Fit | null;
  excluded: Exclusions;
  x: Metric;
  y: Metric;
  size: Metric | null;
  /** Players the axes could not measure at all, named so they can be reported. */
  unmeasured: string[];
}

export function selectPlotted(
  players: readonly AnalysisPlayer[],
  view: ScatterView,
): Selection | null {
  const x = metric(view.x);
  const y = metric(view.y);
  if (!x || !y) return null;
  const size = metric(view.size);

  const excluded: Exclusions = {
    minutes: 0,
    position: 0,
    club: 0,
    ownership: 0,
    price: 0,
    noValue: 0,
  };
  const unmeasured: string[] = [];
  const kept: { player: AnalysisPlayer; x: number; y: number }[] = [];

  for (const player of players) {
    if (
      view.positions.length > 0 &&
      !view.positions.includes(player.position)
    ) {
      excluded.position += 1;
      continue;
    }
    if (view.clubs.length > 0 && !view.clubs.includes(player.club)) {
      excluded.club += 1;
      continue;
    }
    if (player.minutes < view.minMinutes) {
      excluded.minutes += 1;
      continue;
    }
    if (
      player.priceTenths < view.priceFromTenths ||
      player.priceTenths > view.priceToTenths
    ) {
      excluded.price += 1;
      continue;
    }
    // An archived season records no ownership, so the band cannot judge him.
    // Filtering on a figure that was never taken would empty the chart.
    if (
      player.ownership !== null &&
      (player.ownership < view.ownedFrom || player.ownership > view.ownedTo)
    ) {
      excluded.ownership += 1;
      continue;
    }

    const xValue = x.value(player);
    const yValue = y.value(player);
    if (xValue === null || yValue === null) {
      excluded.noValue += 1;
      if (unmeasured.length < 8) unmeasured.push(player.name);
      continue;
    }
    // A log axis cannot show a zero, and substituting a small number would put
    // him somewhere he is not.
    if ((view.logX && xValue <= 0) || (view.logY && yValue <= 0)) {
      excluded.noValue += 1;
      continue;
    }

    kept.push({ player, x: xValue, y: yValue });
  }

  const centres =
    kept.length === 0
      ? null
      : {
          x: centre(
            kept.map((entry) => entry.x),
            view.centreMode,
          )!,
          y: centre(
            kept.map((entry) => entry.y),
            view.centreMode,
          )!,
        };

  const fit = view.trend ? leastSquaresFit(kept) : null;
  // A club short name matches everyone at that club, `@POS` everyone in that
  // position, and `#code` matches one man.
  const highlighted = new Set(view.highlights);

  const points = kept.map<PlottedPlayer>((entry) => {
    const quadrant = centres
      ? quadrantOf(entry, centres)
      : ("low-low" as Quadrant);
    return {
      player: entry.player,
      x: entry.x,
      y: entry.y,
      size: size ? size.value(entry.player) : null,
      quadrant,
      residual: fit ? residualOf(entry, fit) : null,
      // Everything drawn is inside the ownership band now, so the old flag for
      // "strong and unowned" is the whole chart rather than a subset of it.
      overlooked: inStrongQuadrant(quadrant, x, y),
      matched:
        highlighted.size === 0 ||
        highlighted.has(entry.player.club) ||
        // `@MID` isolates a position. Prefixed so it can never collide with a
        // club that happens to share the three letters.
        highlighted.has(`@${entry.player.position}`) ||
        highlighted.has(`#${String(entry.player.code)}`),
    };
  });

  return { points, centres, fit, excluded, x, y, size, unmeasured };
}

/**
 * The corner that is good on both axes.
 *
 * Which corner that is depends on the metrics: high ownership is not a virtue,
 * so "strong" on an ownership axis is the low half.
 */
function inStrongQuadrant(quadrant: Quadrant, x: Metric, y: Metric): boolean {
  const [horizontal, vertical] = quadrant.split("-") as [
    "high" | "low",
    "high" | "low",
  ];
  const goodX = x.higherIsBetter ? horizontal === "high" : horizontal === "low";
  const goodY = y.higherIsBetter ? vertical === "high" : vertical === "low";
  return goodX && goodY;
}

/**
 * What the corner means, in the words of the two stats chosen.
 *
 * Built from the metric labels rather than a lookup table, so a pairing nobody
 * anticipated still gets a caption instead of a blank. Labels keep their own
 * casing: "xGI" and "DefCon" are names, and lowercasing them produced "xgi".
 */
export function quadrantCaption(
  quadrant: Quadrant,
  x: Metric,
  y: Metric,
): string {
  const [horizontal, vertical] = quadrant.split("-") as [
    "high" | "low",
    "high" | "low",
  ];
  return `${horizontal} ${x.label} / ${vertical} ${y.label}`;
}
