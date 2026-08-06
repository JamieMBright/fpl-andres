import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { rateFixtureRun, type FixtureRun } from "../state/fixture-run";

/**
 * Audit items #116 and #118, measured before either is done, and both declined.
 *
 * #116 asks for the player pool table to be virtualised "instead of capping
 * rows at 200". #118 asks for its cells to be memoised. Both read the cap as a
 * performance workaround. It is not one, on two counts.
 *
 * Measured on an idle machine, in jsdom, per re-render:
 *
 *   200 rows -- the shipped cap ------  7.4 ms
 *   700 rows -- the entire FPL pool -- 25.2 ms
 *
 * jsdom is slower than a real browser by roughly two to five times, so a
 * browser renders the shipped table in two to four milliseconds and the whole
 * pool in under ten. An animation frame is 16.7 ms. The cap is not holding back
 * a performance problem, because there is not one to hold back.
 *
 * Second, the cap is a product decision the page already states: rows are
 * sorted before slicing, so the 200 shown are the best 200 by whatever the
 * reader chose, and a line underneath says how many were left out.
 * Virtualising would replace an explained limit with a scrollbar that behaves
 * differently from a scrollbar, keyboard navigation that has to be rebuilt,
 * and find-in-page that stops working -- to solve nothing.
 *
 * Memoising has the same answer from the other end. React charges for a
 * comparison on every render including the cheap ones, and the row objects are
 * rebuilt by the sort each time, so a shallow memo would compare and then
 * re-render anyway.
 *
 * WHAT IS ASSERTED IS A RATIO, NOT A DURATION. The numbers above were taken on
 * an idle machine; the same code measured two to three times slower inside a
 * loaded parallel test run, so an absolute bound here would be a test of how
 * busy the CPU is and would fail on a shared runner. A ratio divides that out.
 * Linearity is also the property that actually decides the question: a table
 * costing proportionally more per row as rows are added is one where a cap is
 * load-bearing. This one is not.
 *
 * The two sides of the ratio are measured INTERLEAVED rather than one after the
 * other. Measuring all the small samples and then all the large ones only
 * divides out load that is steady for the whole run: a burst arriving during
 * the second block lands entirely in the numerator, and the ratio blows past
 * the bound on a table whose scaling never changed. Alternating them puts any
 * burst on both sides, which is what makes the division work.
 */

const HERE = dirname(fileURLToPath(import.meta.url));

interface Row {
  code: number;
  name: string;
  position: string;
  available: boolean;
  priceTenths: number;
  expectedPoints: number;
  perMillion: number;
  returnRate: number;
  ceiling: number;
  appearances: number;
  run: FixtureRun;
}

function rows(count: number): Row[] {
  const run = rateFixtureRun(new Map(), [], 1, "MID", 5);
  return Array.from({ length: count }, (_, index) => ({
    code: 900_000 + index,
    name: `Player ${index}`,
    position: (["GKP", "DEF", "MID", "FWD"] as const)[index % 4] ?? "MID",
    available: index % 17 !== 0,
    priceTenths: 40 + (index % 90),
    expectedPoints: 2 + (index % 60) / 10,
    perMillion: 0.3 + (index % 40) / 100,
    returnRate: (index % 50) / 100,
    ceiling: 6 + (index % 12),
    appearances: 10 + (index % 28),
    run,
  }));
}

function Table({ data }: { data: Row[] }) {
  return (
    <table>
      <tbody>
        {data.map((player) => (
          <tr key={player.code}>
            <th scope="row" translate="no">
              {player.name}
              {player.available ? null : <span className="pool-flag"> ⚑</span>}
            </th>
            <td className="mono">{player.position}</td>
            <td className="mono">{(player.priceTenths / 10).toFixed(1)}</td>
            <td className="mono">{player.expectedPoints.toFixed(2)}</td>
            <td className="mono">{player.perMillion.toFixed(2)}</td>
            <td className="mono">{(player.returnRate * 100).toFixed(0)}%</td>
            <td className="mono">{player.ceiling.toFixed(1)}</td>
            <td className="mono">{player.appearances}</td>
            <td className="mono">
              {player.run.rating === null ? "—" : player.run.rating.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Median rather than mean: one scheduler hiccup should not move the answer. */
function median(values: number[]): number {
  const sorted = [...values].sort((one, other) => one - other);
  return sorted[Math.floor(sorted.length / 2)] ?? 0;
}

/**
 * Re-render both table sizes the same number of times, alternating.
 *
 * Returns the median cost of each. Both are mounted before either is timed, so
 * neither pays the other's warm-up.
 */
function interleavedRerenderMs(
  small: number,
  large: number,
  samples: number,
): { small: number; large: number } {
  const smallData = rows(small);
  const largeData = rows(large);
  const smallView = render(<Table data={smallData} />);
  const largeView = render(<Table data={largeData} />);
  smallView.rerender(<Table data={[...smallData]} />);
  largeView.rerender(<Table data={[...largeData]} />);

  const smallTimings: number[] = [];
  const largeTimings: number[] = [];
  for (let index = 0; index < samples; index += 1) {
    // A fresh array each time, which is what an unrelated parent state change
    // actually produces.
    const smallStartedAt = performance.now();
    smallView.rerender(<Table data={[...smallData]} />);
    smallTimings.push(performance.now() - smallStartedAt);

    const largeStartedAt = performance.now();
    largeView.rerender(<Table data={[...largeData]} />);
    largeTimings.push(performance.now() - largeStartedAt);
  }
  smallView.unmount();
  largeView.unmount();
  return { small: median(smallTimings), large: median(largeTimings) };
}

describe("player pool table render cost", () => {
  it("scales linearly with rows, so the cap is not holding back a cliff", () => {
    // 3.5x the rows should cost about 3.5x the time. Anything superlinear --
    // an O(n^2) layout, a per-row scan of the whole list -- is the shape that
    // makes a cap load-bearing and virtualisation worth its cost.
    const { small, large } = interleavedRerenderMs(200, 700, 15);

    expect(small).toBeGreaterThan(0);
    // 3.5x rows, allowed up to 7x the time before this is called superlinear.
    // Measured ratio on an idle machine is about 3.4.
    expect(large / small).toBeLessThan(7);
  });

  it("renders every row, so the measurement is of the whole table", () => {
    // A component that quietly stopped rendering rows would measure faster and
    // look like an improvement.
    const { container } = render(<Table data={rows(200)} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(200);
  });

  it("sorts before slicing, which is what makes the cap defensible", () => {
    // The 200 shown are the best 200 by whatever the reader chose, not an
    // arbitrary 200. If slicing ever moved above the sort, the cap would start
    // hiding the player somebody filtered for, and the argument for keeping it
    // would stop being true.
    const source = readFileSync(resolve(HERE, "PlayerPoolTable.tsx"), "utf8");
    expect(source.indexOf(".sort(")).toBeGreaterThan(-1);
    expect(source.indexOf(".sort(")).toBeLessThan(
      source.indexOf(".slice(0, 200)"),
    );
    expect(source).toContain("Showing the first 200 of");
  });
});
