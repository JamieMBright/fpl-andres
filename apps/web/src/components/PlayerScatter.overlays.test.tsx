import { fireEvent, render, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlayerScatter } from "./PlayerScatter";
import type { AnalysisPlayer } from "../state/analysis-pool";
import { selectPlotted } from "../state/scatter-select";
import { DEFAULT_VIEW } from "../state/scatter-view";
import { SEASON_PLAYERS } from "../state/season-solver";

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
      clearancesBlocksInterceptions: index % 90,
      tackles: index % 40,
      recoveries: index % 120,
      understat: null,
    };
  });
}

describe("highlighting a player", () => {
  // Index 1, not 0: the default x axis is defensive contribution, which is null
  // for a keeper, so every fourth player in this pool is never plotted at all.
  const ONE_DEFENDER = "#900001";
  const ALL_DEFENDERS = "C1";

  function draw(highlights: string[]) {
    const view = { ...DEFAULT_VIEW, highlights, labels: false };
    const selection = selectPlotted(pool(200), view)!;
    return render(
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    ).container;
  }

  it("lights the chosen player rather than hiding everybody else", () => {
    const container = draw([ONE_DEFENDER]);

    expect(container.querySelectorAll(".scatter-mark-highlit")).toHaveLength(1);
    // The rest are still drawn, still coloured and still hoverable. A chart
    // that answers "where is he" by deleting the pool is not a scatter.
    expect(
      container.querySelectorAll(".scatter-mark-receded").length,
    ).toBeGreaterThan(100);
  });

  it("names him even with labels turned off", () => {
    const container = draw([ONE_DEFENDER]);

    // Somebody who typed a name wants to see whose mark lit up.
    expect(container.querySelectorAll(".scatter-label-highlit")).toHaveLength(
      1,
    );
    expect(container.querySelectorAll(".scatter-label")).toHaveLength(1);
  });

  it("lights nobody when nothing is highlighted", () => {
    const container = draw([]);

    expect(container.querySelectorAll(".scatter-mark-highlit")).toHaveLength(0);
    expect(container.querySelectorAll(".scatter-mark-receded")).toHaveLength(0);
  });

  it("lights a whole club when a club is named", () => {
    const one = draw([ONE_DEFENDER]).querySelectorAll(".scatter-mark-highlit");
    const club = draw([ALL_DEFENDERS]).querySelectorAll(
      ".scatter-mark-highlit",
    );

    expect(club.length).toBeGreaterThan(one.length);
  });
});

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
    // Shading is on by default now, so the off state has to be asked for.
    const view = { ...DEFAULT_VIEW, sweetSpot: false };
    const selection = selectPlotted(pool(200), view)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={view}
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
    const hidden = { ...DEFAULT_VIEW, labels: false };
    const off = selectPlotted(pool(40), hidden)!;
    const plain = render(
      <PlayerScatter
        selection={off}
        view={hidden}
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

  it("clips trend, frontier, marks and labels to the plotting rectangle", () => {
    const view = { ...DEFAULT_VIEW, frontier: true, trend: true, labels: true };
    const selection = selectPlotted(pool(200), view)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );
    const clip = container.querySelector("clipPath")?.id;
    expect(clip).toBeTruthy();
    const clipped = container.querySelector(`g[clip-path="url(#${clip})"]`);
    expect(clipped?.querySelector(".scatter-trend")).not.toBeNull();
    expect(clipped?.querySelector(".scatter-frontier")).not.toBeNull();
    expect(clipped?.querySelector(".scatter-marks")).not.toBeNull();
    expect(clipped?.querySelector(".scatter-labels")).not.toBeNull();
  });
});

describe("scatter tooltip evidence", () => {
  it("shows every active encoding and the five-gameweek projection", () => {
    const published = SEASON_PLAYERS.find(
      (player) => player.position === "DEF",
    );
    expect(published).toBeDefined();
    const [subject] = pool(1);
    expect(subject).toBeDefined();
    const player = {
      ...subject!,
      code: published!.code,
      position: "DEF",
      minutes: 1800,
      ownership: 4.2,
      defensiveContributionPer90: 5,
      defconBarRatio: 0.5,
      expectedGoalInvolvements: 8,
      ninetiesPlayed: 20,
    } satisfies AnalysisPlayer;
    const view = {
      ...DEFAULT_VIEW,
      x: "defconPer90",
      y: "xGIPer90",
      size: "ownership",
      colourBy: "metric" as const,
      colourMetric: "totalPoints",
      minMinutes: 0,
    };
    const selection = selectPlotted([player], view)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={view}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );

    fireEvent.mouseEnter(container.querySelector(".scatter-mark")!);
    const stats = container.querySelector<HTMLElement>(
      ".scatter-tooltip-stats",
    )!;
    expect(within(stats).getByText("DefCon per 90")).toBeInTheDocument();
    expect(within(stats).getByText("xGI per 90")).toBeInTheDocument();
    expect(within(stats).getByText("Ownership")).toBeInTheDocument();
    expect(within(stats).getByText("Total points")).toBeInTheDocument();
    expect(within(stats).getByText("xPts over 5 GW")).toBeInTheDocument();
    expect(within(stats).getByText("Minutes")).toBeInTheDocument();
  });
});
