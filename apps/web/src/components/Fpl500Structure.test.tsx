import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Fpl500Structure } from "./Fpl500Structure";

describe("Fpl500Structure", () => {
  it("shows a legal kit-based popularity squad and positional spend", () => {
    render(
      <Fpl500Structure
        holdings={[
          {
            elementId: 1,
            name: "Starter keeper",
            code: 101,
            position: "GKP",
            club: "ARS",
            priceTenths: 50,
            ownedShare: 0.8,
            startedShare: 0.7,
            captainedShare: 0,
            effectiveOwnership: 0.7,
          },
          {
            elementId: 2,
            name: "Bench keeper",
            code: 102,
            position: "GKP",
            club: "BHA",
            priceTenths: 45,
            ownedShare: 0.6,
            startedShare: 0.1,
            captainedShare: 0,
            effectiveOwnership: 0.1,
          },
          ...Array.from({ length: 13 }, (_, index) => ({
            elementId: index + 3,
            name: `Outfield ${String(index + 1)}`,
            code: 103 + index,
            position: (index < 5 ? "DEF" : index < 10 ? "MID" : "FWD") as
              "DEF" | "MID" | "FWD",
            club: "ARS",
            priceTenths: 60,
            ownedShare: 0.5,
            startedShare: 0.5,
            captainedShare: 0,
            effectiveOwnership: 0.5,
            lastWeekPoints: 4,
          })),
        ]}
        structure={{
          keeperPairings: [
            { starterElementId: 1, benchElementId: 2, count: 240, share: 0.48 },
          ],
          commonStartingXi: {
            method: "modal-formation-most-started",
            formation: [4, 4, 2],
            elementIds: [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
          },
          popularitySquad: {
            method: "legal-aggregate-popularity",
            squad: Array.from({ length: 15 }, (_, index) => index + 1),
            starters: [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13],
            bench: [2, 12, 14, 15],
            formation: [5, 4, 1],
            spentTenths: 875,
            xiSpentTenths: 670,
            bankTenths: 125,
            meanOwnership: 0.52,
            meanStartedShare: 0.47,
            rawGameweekPoints: 58,
          },
          positionalSpend: {
            GKP: {
              mean: 90,
              median: 90,
              p10: 85,
              p90: 95,
              minimum: 80,
              maximum: 100,
            },
            DEF: {
              mean: 250,
              median: 250,
              p10: 230,
              p90: 270,
              minimum: 220,
              maximum: 290,
            },
            MID: {
              mean: 400,
              median: 400,
              p10: 380,
              p90: 420,
              minimum: 360,
              maximum: 440,
            },
            FWD: {
              mean: 260,
              median: 260,
              p10: 240,
              p90: 280,
              minimum: 230,
              maximum: 300,
            },
          },
        }}
      />,
    );

    expect(screen.getByText("The FPL500 popularity squad")).toBeVisible();
    expect(screen.getByText("£87.5m")).toBeVisible();
    expect(screen.getByText("£12.5m")).toBeVisible();
    expect(screen.getByText("58 raw")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Bench" })).toBeVisible();
    expect(document.querySelectorAll(".ceefax-shirt")).toHaveLength(15);
    expect(screen.getByRole("button", { name: /Bench keeper/i })).toBeEnabled();
    expect(screen.queryByText("Goalkeeper pairs")).not.toBeInTheDocument();
    expect(screen.getByText("£40.0m")).toBeVisible();
    expect(screen.getByText("£38.0–£42.0m")).toBeVisible();
  });
});
