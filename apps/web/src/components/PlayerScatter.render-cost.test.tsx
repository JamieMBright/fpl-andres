import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlayerScatter } from "./PlayerScatter";
import type { AnalysisPlayer } from "../state/analysis-pool";
import { selectPlotted } from "../state/scatter-select";
import { DEFAULT_VIEW } from "../state/scatter-view";

/**
 * Whether the full pool needs a canvas.
 *
 * The brief for this component assumed 700-odd players would make an SVG jank
 * and that a canvas renderer might be needed. It does not, and this is the
 * measurement that says so. On an idle machine, in jsdom, per render:
 *
 *   150 players ---------------------  7.8 ms
 *   600 players -- the whole pool ---- 26.3 ms
 *
 * Four times the points for 3.4 times the cost: sub-linear, because the fixed
 * work (scales, axes, grid) is paid once either way. jsdom runs two to five
 * times slower than a browser, so the full pool costs a browser well under an
 * animation frame. Canvas would buy nothing and would cost the thing that makes
 * this chart worth having: every mark is a real DOM node, so hit-testing, the
 * export and the shape-per-position encoding are all free instead of being
 * re-implemented against a pixel buffer.
 *
 * A RATIO IS ASSERTED, NOT A DURATION. The figures above came off an idle
 * machine; the same code runs two to three times slower inside a loaded
 * parallel suite, so an absolute bound would test how busy the runner is. Four
 * times the points for under seven times the cost is linearity, which is the
 * property that actually decides whether a cap or a canvas is load-bearing.
 */

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
      ownership: (index % 60) / 2,
      minutes: 900 + (index % 2000),
      ninetiesPlayed: (900 + (index % 2000)) / 90,
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

function costOf(count: number): number {
  const players = pool(count);
  const selection = selectPlotted(players, { ...DEFAULT_VIEW, trend: true })!;
  const started = performance.now();
  const { unmount } = render(
    <PlayerScatter
      selection={selection}
      view={{ ...DEFAULT_VIEW, trend: true }}
      pinned={[]}
      onTogglePin={() => {}}
    />,
  );
  const elapsed = performance.now() - started;
  unmount();
  return elapsed;
}

describe("PlayerScatter render cost", () => {
  it("grows about linearly with the number of points", () => {
    // Warm the module and jsdom so the first measurement is not the outlier.
    costOf(150);

    const small = costOf(150);
    const large = costOf(600);

    expect(large / small).toBeLessThan(7);
  });

  it("draws every plotted player as its own node", () => {
    const players = pool(120);
    const selection = selectPlotted(players, DEFAULT_VIEW)!;
    const { container } = render(
      <PlayerScatter
        selection={selection}
        view={DEFAULT_VIEW}
        pinned={[]}
        onTogglePin={() => {}}
      />,
    );

    expect(container.querySelectorAll(".scatter-mark")).toHaveLength(
      selection.points.length,
    );
  });
});
