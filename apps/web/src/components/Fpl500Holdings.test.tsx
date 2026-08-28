import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Fpl500Holdings } from "./Fpl500Holdings";

const HOLDINGS = [
  {
    elementId: 1,
    name: "Starter keeper",
    position: "GKP" as const,
    club: "ARS",
    ownedShare: 0.8,
    startedShare: 0.7,
    captainedShare: 0,
    effectiveOwnership: 0.7,
  },
  {
    elementId: 2,
    name: "Bench keeper",
    position: "GKP" as const,
    club: "BHA",
    ownedShare: 0.6,
    startedShare: 0.1,
    captainedShare: 0,
    effectiveOwnership: 0.1,
  },
];

describe("Fpl500Holdings", () => {
  it("keeps goalkeeper pairings inside the goalkeeper tabs", () => {
    render(
      <Fpl500Holdings
        event={1}
        holdings={HOLDINGS}
        keeperPairings={[
          { starterElementId: 1, benchElementId: 2, count: 240, share: 0.48 },
        ]}
      />,
    );

    expect(screen.getByRole("tab", { name: "Players" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: "Pairings" }));

    expect(screen.getByText("Starter keeper + Bench keeper")).toBeVisible();
    expect(screen.getByText("48% · 240 squads")).toBeVisible();
  });

  it("switches goalkeeper tabs with arrow keys", () => {
    render(
      <Fpl500Holdings event={1} holdings={HOLDINGS} keeperPairings={[]} />,
    );
    const players = screen.getByRole("tab", { name: "Players" });

    fireEvent.keyDown(players, { key: "ArrowRight" });

    expect(screen.getByRole("tab", { name: "Pairings" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
