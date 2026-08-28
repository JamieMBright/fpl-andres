import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Fpl500Structure } from "./Fpl500Structure";

describe("Fpl500Structure", () => {
  it("shows the common XI, keeper pairs and positional spend", () => {
    render(
      <Fpl500Structure
        holdings={[
          {
            elementId: 1,
            name: "Starter keeper",
            position: "GKP",
            club: "ARS",
            ownedShare: 0.8,
            startedShare: 0.7,
            captainedShare: 0,
            effectiveOwnership: 0.7,
          },
          {
            elementId: 2,
            name: "Bench keeper",
            position: "GKP",
            club: "BHA",
            ownedShare: 0.6,
            startedShare: 0.1,
            captainedShare: 0,
            effectiveOwnership: 0.1,
          },
          ...Array.from({ length: 10 }, (_, index) => ({
            elementId: index + 3,
            name: `Outfield ${String(index + 1)}`,
            position: (index < 4 ? "DEF" : index < 8 ? "MID" : "FWD") as
              "DEF" | "MID" | "FWD",
            club: "ARS",
            ownedShare: 0.5,
            startedShare: 0.5,
            captainedShare: 0,
            effectiveOwnership: 0.5,
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

    expect(screen.getByText("Most common XI")).toBeVisible();
    expect(screen.getByText("Starter keeper + Bench keeper")).toBeVisible();
    expect(screen.getByText("48%")).toBeVisible();
    expect(screen.getByText("£40.0m")).toBeVisible();
    expect(screen.getByText("£38.0–£42.0m")).toBeVisible();
  });
});
