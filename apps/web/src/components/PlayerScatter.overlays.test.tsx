import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlayerScatter } from "./PlayerScatter";
import type { AnalysisPlayer } from "../state/analysis-pool";
import { selectPlotted } from "../state/scatter-select";
import { DEFAULT_VIEW } from "../state/scatter-view";

function pool(count: number): AnalysisPlayer[] {
  return Array.from({ length: count }, (_, index) => {
    const position = (["GKP", "DEF", "MID", "FWD"] as const)[index % 4]!;
    return {
      elementId: index + 1,
      code: 900_000 + index,
      name: `Player ${index}`,
      position,
      club: `C${index % 20}`,
      teamId: (index % 20) + 1,
      teamCode: (index % 20) + 1,
      available: true,
      priceTenths: 40 + (index % 90),
      // Inside the default 0.1-8% band and over the 1500-minute floor, so the
      // fixture measures the overlays rather than the filters.
      ownership: 0.2 + (index % 70) / 10,
      minutes: 1600 + (index % 1800),
      ninetiesPlayed: (1600 + (index % 1800)) / 90,
      totalPoints: 40 + (index % 160),
      bonus: index % 30,
      expectedGoals: (index % 25) / 2,
      expectedAssists: (index % 13) / 2,
      expectedGoalInvolvements: (index % 30) / 2,
      ictIndex: index % 380,
      influence: index % 1200,
      creativity: index % 1900,
      threat: index % 1500,
      defensiveContribution: index % 500,
      defensiveContributionPer90: (index % 160) / 10,
      defconBarRatio: position === "GKP" ? null : (index % 160) / 100,
      understat: null,
    };
  });
}

describe("scatter overlays", () => {
  it("shades the good corner when it is asked to", () => {
    const view = { ...DEFAULT_VIEW, sweetSpot: true };
    const selection = selectPlotted(pool(200), view)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    expect(selection.points.length).toBeGreaterThan(20);
    // Two gradients, one per axis. Shading is a property of the reference
    // lines, so unlike the ring it draws whatever the axes happen to be.
    expect(container.querySelectorAll(".scatter-shade")).toHaveLength(2);
    expect(container.querySelectorAll("linearGradient")).toHaveLength(2);
  });

  it("leaves the chart unshaded when it is not asked to", () => {
    const selection = selectPlotted(pool(200), DEFAULT_VIEW)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={DEFAULT_VIEW}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    expect(container.querySelector(".scatter-shade")).toBeNull();
  });

  it("shades the good corner harder than the bad one", () => {
    // Equal alpha left the green invisible against the surface while the red
    // still read, so the shading looked like it only marked bad players.
    const view = { ...DEFAULT_VIEW, sweetSpot: true };
    const selection = selectPlotted(pool(200), view)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    const opacities = [...container.querySelectorAll("stop")]
      .map((stop) => Number(stop.getAttribute("stop-opacity")))
      .filter((value) => value > 0);

    expect(Math.max(...opacities)).toBeGreaterThan(Math.min(...opacities));
    expect(Math.max(...opacities)).toBeGreaterThan(0.2);
  });

  it("names every point only when asked", () => {
    const off = selectPlotted(pool(40), DEFAULT_VIEW)!;
    const plain = render(
      <PlayerScatter
        selection={off}
        view={DEFAULT_VIEW}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    expect(plain.container.querySelectorAll(".scatter-label")).toHaveLength(0);
    plain.unmount();

    const view = { ...DEFAULT_VIEW, labels: true };
    const on = selectPlotted(pool(40), view)!;
    const { container } = render(
      <PlayerScatter
        selection={on}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    expect(container.querySelectorAll(".scatter-label")).toHaveLength(
      on.points.length,
    );
    // Each name gets a leader back to its mark, or it belongs to nothing.
    expect(container.querySelectorAll(".scatter-label-whisker")).toHaveLength(
      on.points.length,
    );
  });

  it("says so on the axes when the filters leave nobody", () => {
    const view = { ...DEFAULT_VIEW, minMinutes: 4000 };
    const selection = selectPlotted(pool(200), view)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    expect(selection.points).toHaveLength(0);
    expect(container.querySelector(".scatter-empty-title")?.textContent).toBe(
      "Nothing survives these filters",
    );
  });

  it("draws the frontier when it is asked for", () => {
    const view = { ...DEFAULT_VIEW, frontier: true };
    const selection = selectPlotted(pool(200), view)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    expect(container.querySelector(".scatter-frontier")).not.toBeNull();
  });
});
