import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BarChart, SeasonLines } from "./CalibrationCharts";

/**
 * The charts replaced tables, so they have to carry what a table carried.
 *
 * A bar chart that drops a row, sorts the wrong way, or scales one panel
 * differently from the next is worse than the table it replaced: a table is at
 * least hard to misread. These pin the parts that would fail silently.
 */

describe("BarChart", () => {
  const data = [
    { label: "middle", value: 5 },
    { label: "best", value: 9 },
    { label: "worst", value: 1 },
  ];

  it("ranks by the thing it is measuring, not by name", () => {
    const { container } = render(
      <BarChart title="t" caption="c" data={data} />,
    );
    const labels = [...container.querySelectorAll(".calibration-label")].map(
      (node) => node.textContent,
    );
    expect(labels).toEqual(["best", "middle", "worst"]);
  });

  it("puts the smallest first when smaller is better", () => {
    const { container } = render(
      <BarChart title="t" caption="c" data={data} higherIsBetter={false} />,
    );
    const labels = [...container.querySelectorAll(".calibration-label")].map(
      (node) => node.textContent,
    );
    expect(labels).toEqual(["worst", "middle", "best"]);
  });

  it("draws every row it was given", () => {
    const { container } = render(
      <BarChart title="t" caption="c" data={data} />,
    );
    expect(container.querySelectorAll(".calibration-bar")).toHaveLength(3);
  });

  it("drops a row it cannot measure rather than drawing it as zero", () => {
    // Zero and unmeasured are different claims, and a zero-length bar reads as
    // the first.
    const { container } = render(
      <BarChart
        title="t"
        caption="c"
        data={[...data, { label: "silent", value: null }]}
      />,
    );
    const labels = [...container.querySelectorAll(".calibration-label")].map(
      (node) => node.textContent,
    );
    expect(labels).not.toContain("silent");
  });

  it("scales the longest bar to the ceiling, not to the biggest value", () => {
    // The reference is what everybody is failing to reach, so a bar drawn
    // against the winner instead would show the winner as complete.
    const { container } = render(
      <BarChart
        title="t"
        caption="c"
        data={[{ label: "a", value: 5, reference: 10 }]}
      />,
    );
    const bar = container.querySelector(".calibration-bar");
    const track = container.querySelector(".calibration-track");
    expect(Number(bar?.getAttribute("width"))).toBeCloseTo(
      Number(track?.getAttribute("width")) / 2,
      1,
    );
    expect(container.querySelector(".calibration-reference")).not.toBeNull();
  });

  it("marks this project's own row so the eye finds it", () => {
    const { container } = render(
      <BarChart
        title="t"
        caption="c"
        data={[{ label: "mine", value: 5, mine: true }]}
      />,
    );
    expect(container.querySelector(".calibration-bar-mine")).not.toBeNull();
  });

  it("says it is unmeasured rather than drawing an empty frame", () => {
    const { container } = render(
      <BarChart title="t" caption="c" data={[{ label: "a", value: null }]} />,
    );
    expect(container.querySelector(".calibration-empty")).not.toBeNull();
    expect(container.querySelector("svg")).toBeNull();
  });

  it("names the chart for a screen reader", () => {
    const { container } = render(
      <BarChart title="Captain points" caption="c" data={data} />,
    );
    const svg = container.querySelector("svg");
    const labelledBy = svg?.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(
      container.querySelector(`#${CSS.escape(labelledBy!)}`)?.textContent,
    ).toBe("Captain points");
  });
});

describe("SeasonLines", () => {
  const seasons = ["2022-23", "2023-24", "2024-25"];

  it("draws one line per method", () => {
    const { container } = render(
      <SeasonLines
        title="t"
        caption="c"
        seasons={seasons}
        series={[
          { label: "model", points: [0.5, 0.51, 0.52], mine: true },
          { label: "form", points: [0.44, 0.46, 0.47] },
        ]}
      />,
    );
    expect(container.querySelectorAll(".calibration-line")).toHaveLength(2);
    expect(container.querySelectorAll(".calibration-line-mine")).toHaveLength(
      1,
    );
  });

  it("skips a season a method was not scored in without breaking the line", () => {
    const { container } = render(
      <SeasonLines
        title="t"
        caption="c"
        seasons={seasons}
        series={[{ label: "patchy", points: [0.5, null, 0.52] }]}
      />,
    );
    const points = container
      .querySelector(".calibration-line")
      ?.getAttribute("points");
    expect(points?.split(" ")).toHaveLength(2);
  });

  it("refuses to draw a trend through a single season", () => {
    const { container } = render(
      <SeasonLines
        title="t"
        caption="c"
        seasons={["2024-25"]}
        series={[{ label: "one", points: [0.5] }]}
      />,
    );
    expect(container.querySelector(".calibration-empty")).not.toBeNull();
  });

  it("labels each line at its last measured season", () => {
    const { container } = render(
      <SeasonLines
        title="t"
        caption="c"
        seasons={seasons}
        series={[{ label: "model", points: [0.5, 0.51, null] }]}
      />,
    );
    expect(
      container.querySelector(".calibration-series-label")?.textContent,
    ).toBe("model");
  });
});
