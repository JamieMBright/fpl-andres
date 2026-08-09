import {
  DEFAULT_SIZE_METRIC,
  DEFAULT_X_METRIC,
  DEFAULT_Y_METRIC,
  metric,
} from "./analysis-metrics";
import type { CentreMode } from "./scatter-stats";

/**
 * The whole view, in the address bar.
 *
 * A chart someone spent five minutes configuring is worth sending to a mate,
 * and a screenshot loses the filters that make it mean anything. Only what
 * differs from the default is written, so an untouched page has a clean URL.
 *
 * Everything read back is validated. This is a query string, which is to say it
 * is user input, and an unrecognised metric id must not become a selected axis.
 */

export type ColourBy = "position" | "club" | "metric";

/** Bubble size is optional: "none" draws every player the same. */
export const NO_SIZE = "none";

/** Most bins a reader can tell apart at a glance. */
export const MAX_BINS = 8;
export const MIN_BINS = 2;

/** The live season, which is the bootstrap rather than the archive. */
export const LIVE_SEASON = "";

/** A season is thirty-eight gameweeks, and the window is closed at both ends. */
export const FIRST_EVENT = 1;
export const LAST_EVENT = 38;

/** Seasons the archive carries, newest last so the select reads forwards. */
export const ARCHIVED_SEASONS = [
  "2021-22",
  "2022-23",
  "2023-24",
  "2024-25",
  "2025-26",
] as const;

export interface ScatterView {
  x: string;
  y: string;
  size: string;
  logX: boolean;
  logY: boolean;
  /** Turns an axis round, so the good end can be put wherever it reads best. */
  invertX: boolean;
  invertY: boolean;
  colourBy: ColourBy;
  /** The statistic the colour bins, when colouring by one. */
  colourMetric: string;
  bins: number;
  positions: string[];
  clubs: string[];
  minMinutes: number;
  centreMode: CentreMode;
  trend: boolean;
  /** Rings the corner where both axes are at their good end. */
  sweetSpot: boolean;
  /** The best-available curve: nobody is above and to the good side of it. */
  frontier: boolean;
  /** Names every plotted point on a short leader line. */
  labels: boolean;
  /** Only players owned inside this band are drawn. */
  ownedFrom: number;
  ownedTo: number;
  /**
   * Only players costing inside this band are drawn, in tenths.
   *
   * A replacement has to be affordable to be a replacement, so the honest
   * comparison is inside a price bracket rather than a points-per-million axis
   * that puts a £4.0m bench filler beside a £14.0m striker and calls the cheap
   * one better value.
   */
  priceFromTenths: number;
  priceToTenths: number;
  pinned: number[];
  /** Club short names, and player codes prefixed with `#`, to highlight. */
  highlights: string[];
  /** What the table underneath ranks by. Follows the y-axis until changed. */
  tableMetric: string;
  /** A completed season from the archive, or the empty string for the live one. */
  season: string;
  /** The gameweek window totals are re-summed over. Ignored on the live season. */
  fromEvent: number;
  toEvent: number;
}

const POSITIONS = ["GKP", "DEF", "MID", "FWD"];
// 38 matches plus stoppage. A threshold above this can never match anyone.
const MAX_SEASON_MINUTES = 4560;
const MAX_PINNED = 4;
const MAX_HIGHLIGHTS = 12;
/** Nobody is owned by more than everyone. */
export const OWNERSHIP_CAP = 100;
/** Nothing has ever cost this much; the squad budget is £100.0m for fifteen. */
export const PRICE_CAP_TENTHS = 250;

export const DEFAULT_VIEW: ScatterView = {
  x: DEFAULT_X_METRIC,
  y: DEFAULT_Y_METRIC,
  size: DEFAULT_SIZE_METRIC,
  logX: false,
  logY: false,
  invertX: false,
  invertY: false,
  colourBy: "club",
  colourMetric: DEFAULT_Y_METRIC,
  bins: 5,
  positions: [],
  clubs: [],
  // A season and a half of football. Below this a per-90 rate is a small
  // sample wearing a big number, and the chart fills with players nobody can
  // pick anyway.
  minMinutes: 1500,
  centreMode: "median",
  trend: false,
  // The three overlays that make the chart mean something at a glance: which
  // corner is good, where the edge of the pool is, and who each dot is. A
  // reader who has to switch them on has already been shown a cloud of dots.
  sweetSpot: true,
  frontier: true,
  labels: true,
  // A differential is roughly anything under ten per cent owned; the floor
  // drops the hundreds of players nobody has heard of who own nothing.
  ownedFrom: 0.1,
  ownedTo: 8,
  // The whole market, so the band costs nothing until somebody narrows it.
  priceFromTenths: 0,
  priceToTenths: PRICE_CAP_TENTHS,
  pinned: [],
  highlights: [],
  tableMetric: "",
  season: LIVE_SEASON,
  fromEvent: FIRST_EVENT,
  toEvent: LAST_EVENT,
};

export function readScatterView(params: URLSearchParams): ScatterView {
  return {
    x: metricId(params.get("x"), DEFAULT_VIEW.x),
    y: metricId(params.get("y"), DEFAULT_VIEW.y),
    size:
      params.get("size") === NO_SIZE
        ? NO_SIZE
        : metricId(params.get("size"), DEFAULT_VIEW.size),
    logX: flag(params.get("logx")),
    logY: flag(params.get("logy")),
    invertX: flag(params.get("invx")),
    invertY: flag(params.get("invy")),
    colourBy: colourBy(params.get("colour")),
    colourMetric: metricId(params.get("cmetric"), DEFAULT_VIEW.colourMetric),
    bins: bounded(params.get("bins"), DEFAULT_VIEW.bins, MIN_BINS, MAX_BINS),
    positions: list(params.get("pos")).filter((code) =>
      POSITIONS.includes(code),
    ),
    clubs: list(params.get("club")),
    minMinutes: bounded(
      params.get("mins"),
      DEFAULT_VIEW.minMinutes,
      0,
      MAX_SEASON_MINUTES,
    ),
    centreMode: params.get("centre") === "mean" ? "mean" : "median",
    trend: flag(params.get("trend")),
    sweetSpot: flagOr(params.get("ring"), DEFAULT_VIEW.sweetSpot),
    frontier: flagOr(params.get("front"), DEFAULT_VIEW.frontier),
    labels: flagOr(params.get("names"), DEFAULT_VIEW.labels),
    ownedFrom: bounded(
      params.get("from"),
      DEFAULT_VIEW.ownedFrom,
      0,
      OWNERSHIP_CAP,
      1,
    ),
    ownedTo: bounded(
      params.get("to"),
      DEFAULT_VIEW.ownedTo,
      0,
      OWNERSHIP_CAP,
      1,
    ),
    priceFromTenths: bounded(
      params.get("pricefrom"),
      DEFAULT_VIEW.priceFromTenths,
      0,
      PRICE_CAP_TENTHS,
    ),
    priceToTenths: bounded(
      params.get("priceto"),
      DEFAULT_VIEW.priceToTenths,
      0,
      PRICE_CAP_TENTHS,
    ),
    pinned: list(params.get("pin"))
      .map(Number)
      .filter((code) => Number.isInteger(code) && code > 0)
      .slice(0, MAX_PINNED),
    highlights: list(params.get("hl")).slice(0, MAX_HIGHLIGHTS),
    // Empty means "whatever the y-axis is", resolved by the reader rather than
    // frozen here, so changing the axis moves the table with it.
    tableMetric: metricId(params.get("table"), ""),
    season: season(params.get("season")),
    fromEvent: bounded(
      params.get("gwfrom"),
      DEFAULT_VIEW.fromEvent,
      FIRST_EVENT,
      LAST_EVENT,
    ),
    toEvent: bounded(
      params.get("gwto"),
      DEFAULT_VIEW.toEvent,
      FIRST_EVENT,
      LAST_EVENT,
    ),
  };
}

export function writeScatterView(view: ScatterView): string {
  const params = new URLSearchParams();
  const put = (key: string, value: string, fallback: string) => {
    if (value !== fallback) params.set(key, value);
  };
  const putFlag = (
    target: URLSearchParams,
    key: string,
    value: boolean,
    fallback: boolean,
  ) => {
    if (value !== fallback) target.set(key, value ? "1" : "0");
  };

  put("x", view.x, DEFAULT_VIEW.x);
  put("y", view.y, DEFAULT_VIEW.y);
  put("size", view.size, DEFAULT_VIEW.size);
  if (view.logX) params.set("logx", "1");
  if (view.logY) params.set("logy", "1");
  if (view.invertX) params.set("invx", "1");
  if (view.invertY) params.set("invy", "1");
  put("colour", view.colourBy, DEFAULT_VIEW.colourBy);
  if (view.colourBy === "metric") {
    put("cmetric", view.colourMetric, DEFAULT_VIEW.colourMetric);
    put("bins", String(view.bins), String(DEFAULT_VIEW.bins));
  }
  if (view.positions.length > 0) params.set("pos", view.positions.join(","));
  if (view.clubs.length > 0) params.set("club", view.clubs.join(","));
  put("mins", String(view.minMinutes), String(DEFAULT_VIEW.minMinutes));
  put("centre", view.centreMode, DEFAULT_VIEW.centreMode);
  if (view.trend) params.set("trend", "1");
  putFlag(params, "ring", view.sweetSpot, DEFAULT_VIEW.sweetSpot);
  putFlag(params, "front", view.frontier, DEFAULT_VIEW.frontier);
  putFlag(params, "names", view.labels, DEFAULT_VIEW.labels);
  put("from", String(view.ownedFrom), String(DEFAULT_VIEW.ownedFrom));
  put("to", String(view.ownedTo), String(DEFAULT_VIEW.ownedTo));
  put(
    "pricefrom",
    String(view.priceFromTenths),
    String(DEFAULT_VIEW.priceFromTenths),
  );
  put(
    "priceto",
    String(view.priceToTenths),
    String(DEFAULT_VIEW.priceToTenths),
  );
  if (view.pinned.length > 0) {
    params.set("pin", view.pinned.slice(0, MAX_PINNED).join(","));
  }
  if (view.highlights.length > 0) {
    params.set("hl", view.highlights.slice(0, MAX_HIGHLIGHTS).join(","));
  }
  put("table", view.tableMetric, DEFAULT_VIEW.tableMetric);
  put("season", view.season, DEFAULT_VIEW.season);
  // The window only means something against an archived season, so it is left
  // out of a live URL even when it has been moved.
  if (view.season !== LIVE_SEASON) {
    put("gwfrom", String(view.fromEvent), String(DEFAULT_VIEW.fromEvent));
    put("gwto", String(view.toEvent), String(DEFAULT_VIEW.toEvent));
  }

  return params.toString();
}

function colourBy(raw: string | null): ColourBy {
  return raw === "position" || raw === "metric" ? raw : "club";
}

function season(raw: string | null): string {
  return raw && (ARCHIVED_SEASONS as readonly string[]).includes(raw)
    ? raw
    : LIVE_SEASON;
}

function metricId(raw: string | null, fallback: string): string {
  return raw && metric(raw) ? raw : fallback;
}

function flag(raw: string | null): boolean {
  return raw === "1";
}

/** For a flag that is on by default, where absence has to mean on. */
function flagOr(raw: string | null, fallback: boolean): boolean {
  if (raw === "1") return true;
  if (raw === "0") return false;
  return fallback;
}

function list(raw: string | null): string[] {
  return (raw ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function bounded(
  raw: string | null,
  fallback: number,
  low: number,
  high: number,
  /** Ownership is read to a tenth of a per cent; minutes are whole. */
  decimals = 0,
): number {
  if (raw === null) return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  const step = 10 ** decimals;
  return Math.min(high, Math.max(low, Math.round(parsed * step) / step));
}
