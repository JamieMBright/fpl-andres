import { beforeEach, describe, expect, it } from "vitest";

import {
  readColumnOrder,
  readHiddenColumns,
  saveColumnOrder,
  saveHiddenColumns,
  toCsv,
} from "./player-pool-columns";

const DEFAULT_ORDER = ["name", "club", "price", "points"] as const;

beforeEach(() => {
  localStorage.clear();
});

describe("readColumnOrder", () => {
  it("returns the default order when nothing is stored", () => {
    expect(readColumnOrder(localStorage, DEFAULT_ORDER)).toEqual([
      ...DEFAULT_ORDER,
    ]);
  });

  it("returns a saved order as saved", () => {
    saveColumnOrder(localStorage, ["price", "name", "club", "points"]);

    expect(readColumnOrder(localStorage, DEFAULT_ORDER)).toEqual([
      "price",
      "name",
      "club",
      "points",
    ]);
  });

  it("drops a stored key that no longer exists", () => {
    saveColumnOrder(localStorage, ["price", "retired-column", "name"]);

    expect(readColumnOrder(localStorage, DEFAULT_ORDER)).toEqual([
      "price",
      "name",
      "club",
      "points",
    ]);
  });

  it("appends a new column that did not exist when the order was saved", () => {
    saveColumnOrder(localStorage, ["club", "name"]);

    expect(
      readColumnOrder(localStorage, [
        "name",
        "club",
        "price",
        "points",
        "xg",
      ] as const),
    ).toEqual(["club", "name", "price", "points", "xg"]);
  });

  it("recovers from a corrupted value rather than throwing", () => {
    localStorage.setItem("fpl-andres:pool-columns", "not json");

    expect(readColumnOrder(localStorage, DEFAULT_ORDER)).toEqual([
      ...DEFAULT_ORDER,
    ]);
  });
});

describe("hidden columns", () => {
  it("round-trips a hidden set", () => {
    saveHiddenColumns(localStorage, new Set(["price", "club"]));

    expect(readHiddenColumns(localStorage)).toEqual(new Set(["price", "club"]));
  });

  it("is empty when nothing is stored", () => {
    expect(readHiddenColumns(localStorage)).toEqual(new Set());
  });
});

describe("toCsv", () => {
  it("joins a header and rows with CRLF", () => {
    expect(toCsv(["Name", "Club"], [["Salah", "LIV"]])).toBe(
      "Name,Club\r\nSalah,LIV",
    );
  });

  it("quotes a value containing a comma, quote or newline", () => {
    expect(toCsv(["Note"], [['Say "hi", then\nbye']])).toBe(
      'Note\r\n"Say ""hi"", then\nbye"',
    );
  });
});
