import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import validation from "../data/validation.json";
import { ValidationReport } from "./ValidationReport";

function renderReport() {
  return render(
    <MemoryRouter>
      <ValidationReport />
    </MemoryRouter>,
  );
}

describe("the opening gameweek is reported on its own", () => {
  it("publishes the measured GW1 ranking beside the season-long one", () => {
    renderReport();

    const heading = screen.getByRole("heading", {
      name: "How much of that survives gameweek one?",
    });
    expect(heading).toBeVisible();

    const table = screen.getByRole("table", {
      name: /Opening-gameweek rank correlation/i,
    });
    for (const season of validation.seasons) {
      const opening = season.openingGameweek;
      if (!opening) {
        continue;
      }
      const row = within(table).getByRole("row", {
        name: new RegExp(`^${season.season}\\b`),
      });
      // The number a manager locking a squad before kick-off actually gets.
      expect(row).toHaveTextContent(opening.spearman.toFixed(3));
      expect(row).toHaveTextContent(String(opening.scored));
      expect(row).toHaveTextContent(opening.previousSeason);
    }
  });

  it("shows GW1 as the thinner number rather than burying it", () => {
    renderReport();

    // The page claims the opening ranked worse in three of four seasons and
    // names one exception. If the artifact ever stops saying that, the copy is
    // wrong and this test is how it gets caught.
    const compared = validation.seasons
      .map((season) => ({
        opening: season.openingGameweek?.spearman,
        inSeason: season.methods.find((method) => method.label === "model")
          ?.spearman,
      }))
      .filter(
        (pair): pair is { opening: number; inSeason: number } =>
          typeof pair.opening === "number" && typeof pair.inSeason === "number",
      );
    const worse = compared.filter(
      (pair) => pair.opening < pair.inSeason,
    ).length;
    expect(worse).toBe(compared.length - 1);
    expect(screen.getByText(/three of the four seasons/i)).toBeVisible();

    const meanOpening =
      compared.reduce((sum, pair) => sum + pair.opening, 0) / compared.length;
    const meanInSeason =
      compared.reduce((sum, pair) => sum + pair.inSeason, 0) / compared.length;
    expect(meanOpening).toBeLessThan(meanInSeason);

    expect(screen.getByText(/least tested number I publish/i)).toBeVisible();
  });
});
