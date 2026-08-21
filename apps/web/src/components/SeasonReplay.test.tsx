import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

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
  gameweeksPlayed: number;
  seasonGameweeks: number;
  netPoints: number;
  proratedPoints: number;
  weeks: ReplayWeek[];
  benchmark: { managers: number; beaten: number } | null;
};

// The replay lands with the next `validate` run, which reads the corpus out of
// Supabase and cannot be run here. Naming the shape keeps these tests honest
// before the artifact carries it and exact afterwards.
const replays = (validation.seasons as unknown as { replay?: Replay }[])
  .map((season) => season.replay)
  .filter(
    (replay): replay is Replay =>
      Boolean(replay?.weeks?.length) &&
      // An earlier artifact replayed from gameweek one, which the projector
      // cannot support. The component refuses that shape, and so does this.
      typeof replay?.gameweeksPlayed === "number",
  );

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

  it("says how much of the season it covers rather than implying all of it", () => {
    for (const replay of replays) {
      // At or after the start: a season missing its opening gameweek from the
      // corpus begins at the first week it actually has.
      expect(replay.weeks[0]?.event).toBeGreaterThanOrEqual(
        replay.startGameweek,
      );
      expect(replay.gameweeksPlayed).toBe(replay.weeks.length);
      expect(replay.gameweeksPlayed).toBeLessThanOrEqual(
        replay.seasonGameweeks,
      );
    }
    if (replays.length === 0) return;
    renderReplay();
    // The shortfall is the reason the comparison needs pro-rating, so the page
    // has to name it rather than let a part-season read as a whole one.
    expect(screen.getByText(/gameweeks two to six/i)).toBeVisible();
  });

  it("compares a pro-rated pace and says that is what it is", () => {
    if (replays.length === 0) return;
    renderReplay();

    const replay = replays[0]!;
    expect(replay.proratedPoints).toBe(
      Math.round(
        (replay.netPoints * replay.seasonGameweeks) / replay.gameweeksPlayed,
      ),
    );
    if (replay.benchmark) {
      expect(
        screen.getByText(/pro-rated pace rather than a season/i),
      ).toBeVisible();
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

  it("steps to another week when the scrubber moves", () => {
    if (replays.length === 0) return;
    renderReplay();

    const slider = screen.getByRole("slider", { name: "Gameweek" });
    const weekHeading = () =>
      screen.getByRole("heading", { name: /^Gameweek \d+/ }).textContent;
    const first = weekHeading();
    // A range input moves by its value, not by a keystroke userEvent can send.
    fireEvent.change(slider, { target: { value: "1" } });

    expect(weekHeading()).not.toBe(first);
  });

  it("says who it beat rather than claiming a rank it cannot support", () => {
    if (replays.length === 0) return;
    renderReplay();

    const benchmarked = replays[0]?.benchmark;
    if (benchmarked) {
      expect(screen.getByText(/real\s+managers/i)).toBeVisible();
      // The cohort is skewed toward good managers and the page has to say so.
      expect(
        screen.getByText(/ranked one rather than the whole game/i),
      ).toBeVisible();
    } else {
      expect(screen.getByText(/nothing honest to compare/i)).toBeVisible();
    }
  });
});
