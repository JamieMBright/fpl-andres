import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";

import validation from "../data/validation.json";
import { SeasonReplay } from "./SeasonReplay";

type ReplayWeek = {
  event: number;
  points: number;
  runningTotal: number;
  hitPoints: number;
  transfers: unknown[];
};

type Replay = {
  season: string;
  startGameweek: number;
  netPoints: number;
  weeks: ReplayWeek[];
  benchmark: { managers: number; beaten: number } | null;
};

// The replay lands with the next `validate` run, which reads the corpus out of
// Supabase and cannot be run here. Naming the shape keeps these tests honest
// before the artifact carries it and exact afterwards.
const replays = (validation.seasons as unknown as { replay?: Replay }[])
  .map((season) => season.replay)
  .filter((replay): replay is Replay => Boolean(replay?.weeks?.length));

function renderReplay() {
  return render(
    <MemoryRouter>
      <SeasonReplay />
    </MemoryRouter>,
  );
}

describe("the replayed season", () => {
  it("renders a stepper when the artifact carries one, and nothing when it does not", () => {
    const { container } = renderReplay();

    if (replays.length === 0) {
      // Rendering an empty season would imply a measurement that does not exist.
      expect(container).toBeEmptyDOMElement();
      return;
    }
    expect(
      screen.getByRole("heading", { name: /Play the season back/i }),
    ).toBeVisible();
    expect(screen.getByRole("slider", { name: "Gameweek" })).toBeVisible();
  });

  it("opens in gameweek one, so the total covers a whole season", () => {
    for (const replay of replays) {
      expect(replay.startGameweek).toBe(1);
      expect(replay.weeks[0]?.event).toBe(1);
    }
  });

  it("keeps a running total that only moves by the week's net score", () => {
    for (const replay of replays) {
      let running = 0;
      for (const week of replay.weeks) {
        running += week.points - week.hitPoints;
        expect(week.runningTotal).toBe(running);
      }
      expect(replay.weeks.at(-1)?.runningTotal).toBe(replay.netPoints);
    }
  });

  it("never charges a hit in a week it made no transfer", () => {
    for (const replay of replays) {
      for (const week of replay.weeks) {
        if (week.hitPoints > 0) {
          expect(week.transfers.length).toBeGreaterThan(0);
        }
      }
    }
  });

  it("steps to another week when the scrubber moves", async () => {
    if (replays.length === 0) return;
    renderReplay();
    const user = userEvent.setup();

    const slider = screen.getByRole("slider", { name: "Gameweek" });
    const first = screen.getByRole("heading", { level: 3 }).textContent;
    await user.type(slider, "{arrowright}");

    expect(screen.getByRole("heading", { level: 3 }).textContent).not.toBe(
      first,
    );
  });

  it("says who it beat rather than claiming a rank it cannot support", () => {
    if (replays.length === 0) return;
    renderReplay();

    const benchmarked = replays[0]?.benchmark;
    if (benchmarked) {
      expect(screen.getByText(/real\s+managers/i)).toBeVisible();
      // The cohort is skewed toward good managers and the page has to say so.
      expect(
        screen.getByText(/ranked cohort rather than the whole game/i),
      ).toBeVisible();
    } else {
      expect(screen.getByText(/nothing honest to compare/i)).toBeVisible();
    }
  });
});
