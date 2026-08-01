import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { captureDay, deadline, integer, money, timestamp } from "./format";

/**
 * Audit item #117. Five identical `moneyFormatter` definitions lived in five
 * components. They agreed, which is the point: five copies is five chances for
 * one to gain a decimal place and render a price differently on one page.
 *
 * Consolidating them surfaced a divergence that was not identical: timestamps
 * rendered in `Europe/London` while the status strip rendered dates in `UTC`.
 * Both are now deliberate and named, rather than two accidents.
 */

const SOURCE = join(__dirname);

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path) ? [path] : [];
  });
}

describe("shared formatters", () => {
  it("renders money to one decimal place with a pound sign", () => {
    expect(`${money.format(100.4)}m`).toBe("£100.4m");
    expect(`${money.format(4)}m`).toBe("£4.0m");
  });

  it("groups large integers", () => {
    expect(integer.format(1_410_478)).toBe("1,410,478");
  });

  it("renders football times in London, where the deadlines are", () => {
    // 19:00 UTC in August is 20:00 BST. A Saturday 20:00 kick-off is not a
    // 19:00 kick-off, and a user in London is the audience.
    const rendered = timestamp.format(new Date("2026-08-22T19:00:00Z"));
    expect(rendered).toContain("20:00");
  });

  it("renders capture dates in UTC, matching the provenance record", () => {
    // 23:30 UTC on the 1st is 00:30 BST on the 2nd. Rendering the capture time
    // in local time would put two snapshots a minute apart on different days.
    expect(captureDay.format(new Date("2026-08-01T23:30:00Z"))).toBe("1 Aug");
  });

  it("renders a deadline in the timezone the user has to meet it in", () => {
    // The bug this replaces. TransferPlanPanel rendered the deadline with
    // timeZone: "UTC", so the published 2026/27 opening deadline of
    // 2026-08-21T17:30:00Z displayed as 17:30 when a UK user's clock says
    // 18:30 BST. An hour wrong, in the one place on the site where being an
    // hour wrong costs points.
    expect(deadline.format(new Date("2026-08-21T17:30:00Z"))).toContain(
      "18:30",
    );
  });

  it("renders a winter deadline without inventing an hour", () => {
    // GMT, so the instant and the wall clock agree. Proves the London choice is
    // a timezone conversion and not a fixed offset.
    expect(deadline.format(new Date("2026-12-26T11:30:00Z"))).toContain(
      "11:30",
    );
  });

  it("is the only place an Intl formatter is constructed", () => {
    const offenders = sourceFiles(SOURCE)
      .filter((path) => !path.endsWith(join("src", "format.ts")))
      .filter((path) => readFileSync(path, "utf-8").includes("new Intl."))
      .map((path) => path.slice(SOURCE.length + 1));

    expect(offenders).toEqual([]);
  });
});
