import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Fpl500SeasonStanding } from "./Fpl500SeasonStanding";

describe("Fpl500SeasonStanding", () => {
  it("says nothing has been captured yet for an empty cohort", () => {
    render(<Fpl500SeasonStanding rows={[]} />);

    expect(screen.getByText(/no season standing captured/i)).toBeVisible();
  });

  it("defaults to sorting by total points", () => {
    render(
      <Fpl500SeasonStanding
        rows={[
          { overallRank: 900, totalPoints: 50 },
          { overallRank: 200, totalPoints: 300 },
        ]}
      />,
    );

    expect(screen.getByRole("radio", { name: "Total points" })).toBeChecked();
  });

  it("switches to sorting by overall rank on request", () => {
    render(
      <Fpl500SeasonStanding
        rows={[
          { overallRank: 900, totalPoints: 50 },
          { overallRank: 200, totalPoints: 300 },
        ]}
      />,
    );

    screen.getByRole("radio", { name: "Overall rank" }).click();

    expect(screen.getByRole("radio", { name: "Overall rank" })).toBeChecked();
  });

  it("says how many of the five hundred are drawn", () => {
    render(
      <Fpl500SeasonStanding
        rows={[
          { overallRank: 900, totalPoints: 50 },
          { overallRank: 200, totalPoints: 300 },
        ]}
      />,
    );

    expect(screen.getByText(/2 of the five hundred/)).toBeInTheDocument();
  });
});
