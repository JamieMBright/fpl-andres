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

describe("calibration is reported by projected band", () => {
  // The bands land with the next `validate` run, which reads the corpus out of
  // Supabase and cannot be run here. Until that artifact arrives the field is
  // absent from the JSON and therefore from its inferred type, so the shape is
  // named rather than inferred.
  type BandRow = { label: string; count: number };
  const banded = (
    validation.seasons as unknown as {
      methods: { label: string; calibration?: BandRow[] }[];
    }[]
  ).flatMap(
    (season) =>
      season.methods.find((method) => method.label === "model")?.calibration ??
      [],
  );

  it("renders a band table when the artifact carries one, and claims nothing when it does not", () => {
    renderReport();

    const heading = screen.queryByRole("heading", {
      name: "When I say six, what comes back?",
    });
    // The measurement lands with the next validate run. Until then the section
    // must be absent rather than rendered empty or filled with zeroes.
    expect(heading === null).toBe(banded.length === 0);
  });

  it("pools every band across seasons so the top band has rows", () => {
    if (banded.length === 0) {
      return;
    }
    renderReport();

    const table = screen.getByRole("table", {
      name: /Mean projected points against mean actual points/i,
    });
    const labels = new Set(banded.map((band) => band.label));
    for (const label of labels) {
      const total = banded
        .filter((band) => band.label === label)
        .reduce((sum, band) => sum + band.count, 0);
      // Escaped and anchored on whitespace rather than `\b`: the top band is
      // "8+", and there is no word boundary between a plus and the space that
      // follows it.
      const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const row = within(table).getByRole("row", {
        name: new RegExp(`^${escaped}(\\s|$)`),
      });
      expect(row).toHaveTextContent(total.toLocaleString("en-GB"));
    }
  });
});
