import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { expectedXi } from "../state/expected-xi";
import ExpectedXiPage from "./ExpectedXiPage";

describe("Expected XI page", () => {
  it("renders every team with separated evidence labels", () => {
    render(
      <MemoryRouter>
        <ExpectedXiPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Expected XI" })).toBeVisible();
    expect(
      screen.getByRole("navigation", { name: "Expected XI clubs" }),
    ).toBeVisible();
    expect(screen.getAllByRole("link")).toHaveLength(20);
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(20);
    const players = expectedXi().teams.flatMap((team) => [
      ...team.starters,
      ...team.reserves,
    ]);
    expect(
      document.querySelectorAll(".expected-xi-evidence-market"),
    ).toHaveLength(
      players.filter((player) => player.evidence === "market").length,
    );
    expect(
      document.querySelectorAll(".expected-xi-evidence-model"),
    ).toHaveLength(
      players.filter((player) => player.evidence === "model").length,
    );
    expect(document.body).toHaveTextContent("Likely XI");
    expect(document.body).toHaveTextContent("Next in");
  });
});
