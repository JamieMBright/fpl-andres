import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import validation from "../data/validation.json";
import ProofPage from "./ProofPage";

describe("ProofPage", () => {
  it("derives the trust case from the validation artifact", () => {
    render(
      <MemoryRouter>
        <ProofPage />
      </MemoryRouter>,
    );
    const wins = validation.seasons.reduce(
      (total, season) => total + season.league.policies.advised.wins,
      0,
    );
    const leagues = validation.seasons.reduce(
      (total, season) => total + season.league.leaguesPlayed,
      0,
    );
    const freeGain = validation.seasons.reduce(
      (total, season) => total + season.replay.transferReturn.freeGain,
      0,
    );
    const template = validation.captainSignificance.find(
      (entry) => entry.label === "template",
    );

    expect(screen.getByText("16/16")).toBeVisible();
    expect(
      screen.getByText(`+${template?.improvement.toFixed(3)}`),
    ).toBeVisible();
    expect(screen.getByText(`${wins}/${leagues}`)).toBeVisible();
    expect(screen.getByText(`+${freeGain.toFixed(0)}`)).toBeVisible();
    expect(screen.getAllByRole("row")).toHaveLength(
      validation.seasons.length + 1,
    );
  });

  it("links to detail without embedding the full method", () => {
    render(
      <MemoryRouter>
        <ProofPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: "Full calibration" }),
    ).toHaveAttribute("href", "/calibration");
    expect(screen.getByRole("link", { name: "Method" })).toHaveAttribute(
      "href",
      "/methodology",
    );
    expect(screen.getByRole("link", { name: "FPL500" })).toHaveAttribute(
      "href",
      "/fpl500",
    );
    expect(screen.queryByText("The pipeline, step by step")).toBeNull();
    expect(screen.queryByText(/old results view/i)).toBeNull();
  });
});
