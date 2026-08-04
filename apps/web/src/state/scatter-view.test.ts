import { describe, expect, it } from "vitest";

import {
  DEFAULT_VIEW,
  readScatterView,
  writeScatterView,
} from "./scatter-view";

function round(search: string) {
  return readScatterView(new URLSearchParams(search));
}

describe("readScatterView", () => {
  it("is the default view when the URL says nothing", () => {
    expect(readScatterView(new URLSearchParams())).toEqual(DEFAULT_VIEW);
  });

  it("survives a round trip", () => {
    const view = {
      ...DEFAULT_VIEW,
      x: "ownership",
      y: "defconPer90",
      size: "price",
      logX: true,
      colourBy: "club" as const,
      positions: ["DEF", "MID"],
      clubs: ["ARS"],
      minMinutes: 900,
      centreMode: "mean" as const,
      trend: true,
      sweetSpot: true,
      frontier: true,
      ownedFrom: 1.5,
      ownedTo: 12,
      pinned: [154561, 226597],
      search: "wieffer",
    };

    expect(
      readScatterView(new URLSearchParams(writeScatterView(view))),
    ).toEqual(view);
  });

  it("leaves defaults out of the query string", () => {
    expect(writeScatterView(DEFAULT_VIEW)).toBe("");
  });

  /*
   * The query string is user input. An unknown metric id must not reach the
   * axis picker as a selected value that renders a blank chart.
   */
  it("falls back when a metric id is not one we publish", () => {
    expect(round("x=drop%20table&y=xGI").x).toBe(DEFAULT_VIEW.x);
    expect(round("x=drop%20table&y=xGI").y).toBe("xGI");
  });

  it("discards positions and colour modes it does not recognise", () => {
    expect(round("pos=DEF,WIZARD").positions).toEqual(["DEF"]);
    expect(round("colour=vibes").colourBy).toBe(DEFAULT_VIEW.colourBy);
  });

  it("clamps a minutes threshold outside the possible range", () => {
    expect(round("mins=-500").minMinutes).toBe(0);
    expect(round("mins=99999").minMinutes).toBe(4560);
    expect(round("mins=notanumber").minMinutes).toBe(DEFAULT_VIEW.minMinutes);
  });

  it("keeps at most four pinned players, because the panel holds four", () => {
    expect(round("pin=1,2,3,4,5,6").pinned).toEqual([1, 2, 3, 4]);
  });

  it("drops pinned entries that are not player codes", () => {
    expect(round("pin=1,abc,-4,2").pinned).toEqual([1, 2]);
  });

  it("bounds the search term rather than carrying an essay", () => {
    expect(round(`q=${"a".repeat(200)}`).search).toHaveLength(40);
  });
});
