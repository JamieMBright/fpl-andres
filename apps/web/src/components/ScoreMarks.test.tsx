import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreMarks, type ScoreLine } from "./ScoreMarks";

function line(over: Partial<ScoreLine> = {}): ScoreLine {
  return {
    goals: 0,
    assists: 0,
    cleanSheets: 0,
    defensiveContribution: false,
    goalsConceded: 0,
    ownGoals: 0,
    penaltiesMissed: 0,
    penaltiesSaved: 0,
    redCards: 0,
    saves: 0,
    yellowCards: 0,
    bonus: 0,
    haul: false,
    ...over,
  };
}

describe("ScoreMarks", () => {
  it("draws nothing for a blank", () => {
    render(<ScoreMarks line={line()} />);

    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });

  it("repeats the mark rather than carrying a count", () => {
    render(<ScoreMarks line={line({ goals: 2 })} />);

    expect(screen.getAllByRole("img", { name: "Goal" })).toHaveLength(2);
  });

  it("caps a repeat at three and prints the number instead", () => {
    render(<ScoreMarks line={line({ goals: 5 })} />);

    expect(screen.getAllByRole("img", { name: "Goal" })).toHaveLength(3);
    expect(screen.getByText("×5")).toBeInTheDocument();
  });

  it("names the metal a bonus score is worth", () => {
    render(<ScoreMarks line={line({ bonus: 2 })} />);

    expect(
      screen.getByRole("img", { name: "Two bonus points" }),
    ).toBeInTheDocument();
  });

  it("gives every mark a name a screen reader can read", () => {
    render(
      <ScoreMarks
        line={line({
          assists: 1,
          bonus: 3,
          cleanSheets: 1,
          defensiveContribution: true,
          goals: 1,
          haul: true,
        })}
      />,
    );

    const named = screen
      .getAllByRole("img")
      .map((mark) => mark.getAttribute("aria-label") ?? mark.textContent);
    expect(named).toEqual([
      "Haul",
      "Goal",
      "Assist",
      "Clean sheet",
      "Defensive contribution",
      "Three bonus points",
    ]);
  });

  it("keeps a clean sheet and a defensive contribution apart", () => {
    render(<ScoreMarks line={line({ cleanSheets: 1 })} />);

    expect(
      screen.getByRole("img", { name: "Clean sheet" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: "Defensive contribution" }),
    ).not.toBeInTheDocument();
  });

  it("names every detailed scoring mark", () => {
    render(
      <ScoreMarks
        line={line({
          goalsConceded: 2,
          ownGoals: 1,
          penaltiesMissed: 1,
          penaltiesSaved: 1,
          redCards: 1,
          saves: 4,
          yellowCards: 1,
        })}
      />,
    );

    expect(screen.getByRole("img", { name: "4 saves" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "2 goals conceded" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Yellow card" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Red card" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Own goal" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Penalty saved" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Penalty missed" }),
    ).toBeInTheDocument();
  });
});
