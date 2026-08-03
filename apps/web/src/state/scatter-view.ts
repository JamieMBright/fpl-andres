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

export type ColourBy = "position" | "club";

export interface ScatterView {
  x: string;
  y: string;
  size: string;
  logX: boolean;
  logY: boolean;
  colourBy: ColourBy;
  positions: string[];
  clubs: string[];
  minMinutes: number;
  centreMode: CentreMode;
  trend: boolean;
  /** Highlights strong players almost nobody owns. */
  overlooked: boolean;
  overlookedCeiling: number;
  pinned: number[];
  search: string;
}

const POSITIONS = ["GKP", "DEF", "MID", "FWD"];
// 38 matches plus stoppage. A threshold above this can never match anyone.
const MAX_SEASON_MINUTES = 4560;
const MAX_PINNED = 4;
const MAX_SEARCH = 40;

export const DEFAULT_VIEW: ScatterView = {
  x: DEFAULT_X_METRIC,
  y: DEFAULT_Y_METRIC,
  size: DEFAULT_SIZE_METRIC,
  logX: false,
  logY: false,
  colourBy: "club",
  positions: [],
  clubs: [],
  minMinutes: 450,
  centreMode: "median",
  trend: false,
  overlooked: false,
  overlookedCeiling: 5,
  pinned: [],
  search: "",
};

export function readScatterView(params: URLSearchParams): ScatterView {
  return {
    x: metricId(params.get("x"), DEFAULT_VIEW.x),
    y: metricId(params.get("y"), DEFAULT_VIEW.y),
    size: metricId(params.get("size"), DEFAULT_VIEW.size),
    logX: flag(params.get("logx")),
    logY: flag(params.get("logy")),
    colourBy: params.get("colour") === "position" ? "position" : "club",
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
    overlooked: flag(params.get("overlooked")),
    overlookedCeiling: bounded(
      params.get("owned"),
      DEFAULT_VIEW.overlookedCeiling,
      0,
      100,
    ),
    pinned: list(params.get("pin"))
      .map(Number)
      .filter((code) => Number.isInteger(code) && code > 0)
      .slice(0, MAX_PINNED),
    search: (params.get("q") ?? "").slice(0, MAX_SEARCH),
  };
}

export function writeScatterView(view: ScatterView): string {
  const params = new URLSearchParams();
  const put = (key: string, value: string, fallback: string) => {
    if (value !== fallback) params.set(key, value);
  };

  put("x", view.x, DEFAULT_VIEW.x);
  put("y", view.y, DEFAULT_VIEW.y);
  put("size", view.size, DEFAULT_VIEW.size);
  if (view.logX) params.set("logx", "1");
  if (view.logY) params.set("logy", "1");
  put("colour", view.colourBy, DEFAULT_VIEW.colourBy);
  if (view.positions.length > 0) params.set("pos", view.positions.join(","));
  if (view.clubs.length > 0) params.set("club", view.clubs.join(","));
  put("mins", String(view.minMinutes), String(DEFAULT_VIEW.minMinutes));
  put("centre", view.centreMode, DEFAULT_VIEW.centreMode);
  if (view.trend) params.set("trend", "1");
  if (view.overlooked) params.set("overlooked", "1");
  put(
    "owned",
    String(view.overlookedCeiling),
    String(DEFAULT_VIEW.overlookedCeiling),
  );
  if (view.pinned.length > 0) {
    params.set("pin", view.pinned.slice(0, MAX_PINNED).join(","));
  }
  put("q", view.search, DEFAULT_VIEW.search);

  return params.toString();
}

function metricId(raw: string | null, fallback: string): string {
  return raw && metric(raw) ? raw : fallback;
}

function flag(raw: string | null): boolean {
  return raw === "1";
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
): number {
  if (raw === null) return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(high, Math.max(low, Math.round(parsed)));
}
