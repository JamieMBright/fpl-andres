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
});
