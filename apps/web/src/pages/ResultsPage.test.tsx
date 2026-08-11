import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import fpl500 from "../data/fpl500.json";
import validation from "../data/validation.json";
import ResultsPage from "./ResultsPage";

describe("measured results", () => {
  it("derives three evidence cases from published artifacts", () => {
    render(
      <MemoryRouter>
        <ResultsPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Measured Results" }),
    ).toBeVisible();
    for (const heading of [
      "Player ranking",
      "Season simulation",
      "Experienced managers",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeVisible();
    }

    const observations = validation.seasons.reduce(
      (total, season) => total + season.rows,
      0,
    );
    expect(
      screen.getByText(observations.toLocaleString("en-GB")),
    ).toBeVisible();
    expect(
      screen.getByText(fpl500.catalogueSize.toLocaleString("en-GB")),
    ).toBeVisible();
    expect(
      screen.getAllByText(String(validation.seasons.length)).length,
    ).toBeGreaterThan(0);

    expect(
      screen.getByRole("link", { name: "Open full calibration" }),
    ).toHaveAttribute("href", "/calibration");
    expect(
      screen.getByRole("link", { name: "Inspect FPL500" }),
    ).toHaveAttribute("href", "/fpl500");
    expect(
      screen.getByRole("link", { name: "Read the method" }),
    ).toHaveAttribute("href", "/methodology");

    const dates = screen.getAllByRole("time");
    expect(dates).toHaveLength(3);
    expect(dates[0]).toHaveAttribute("datetime", validation.generatedAt);
    expect(dates[2]).toHaveAttribute("datetime", fpl500.generatedAt);
    expect(
      document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href,
    ).toBe("https://fpl-andres.vercel.app/results");
    expect(document.body).not.toHaveTextContent(
      /testimonial|customer review|rating/i,
    );
  });
});
