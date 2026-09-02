import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScatterControls } from "./ScatterControls";
import type { AnalysisPool } from "../state/analysis-pool";
import { DEFAULT_VIEW, LIVE_SEASON } from "../state/scatter-view";

function pool(
  vintage: AnalysisPool["vintage"],
  positions: readonly string[] = ["GKP", "DEF", "MID", "FWD"],
): AnalysisPool {
  return {
    players: [],
    clubs: [],
    positions: [...positions],
    vintage,
    understatCoverage: 0,
    understatSeason: "2025-26",
  };
}

describe("ScatterControls minimum minutes slider", () => {
  it("caps live-season minutes at what has been possible so far", () => {
    render(
      <ScatterControls
        pool={pool({
          state: "live_season",
          season: "2026-27",
          completedGameweeks: 1,
          defaultMinimumMinutes: 80,
        })}
        view={{ ...DEFAULT_VIEW, season: LIVE_SEASON, minMinutes: 80 }}
        onChange={() => {}}
        onReset={() => {}}
        plotted={0}
      />,
    );

    const slider = screen.getByLabelText(/minimum minutes/i);
    expect(slider).toHaveAttribute("max", "90");
    expect(slider).toHaveAttribute("step", "10");
  });

  it("says the threshold scales with gameweeks played, not a fixed number", () => {
    render(
      <ScatterControls
        pool={pool({
          state: "live_season",
          season: "2026-27",
          completedGameweeks: 2,
          defaultMinimumMinutes: 160,
        })}
        view={{ ...DEFAULT_VIEW, season: LIVE_SEASON, minMinutes: 160 }}
        onChange={() => {}}
        onReset={() => {}}
        plotted={0}
      />,
    );

    expect(screen.getByText(/2 gameweeks played so far/)).toBeInTheDocument();
    expect(screen.queryByText(/Five matches is the default/)).toBeNull();
  });

  it("says how many players the minutes threshold is hiding right now", () => {
    render(
      <ScatterControls
        excludedByMinutes={7}
        pool={pool({
          state: "live_season",
          season: "2026-27",
          completedGameweeks: 1,
          defaultMinimumMinutes: 80,
        })}
        view={{ ...DEFAULT_VIEW, season: LIVE_SEASON, minMinutes: 80 }}
        onChange={() => {}}
        onReset={() => {}}
        plotted={0}
      />,
    );

    expect(screen.getByText(/Hiding 7 below it right now/)).toBeInTheDocument();
  });
});
