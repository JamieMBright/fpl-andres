import type { PublicTeamPick } from "@fpl-andres/contracts";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PitchView } from "./PitchView";

type Position = "GKP" | "DEF" | "MID" | "FWD";

function pick(
  squadPosition: number,
  positionCode: Position,
  multiplier: number,
  extra: Partial<PublicTeamPick> = {},
): PublicTeamPick {
  return {
    elementId: 100 + squadPosition,
    squadPosition,
    multiplier,
    isCaptain: false,
    isViceCaptain: false,
    identity: {
      webName: `${positionCode}${squadPosition}`,
      positionCode,
      teamShortName: "TST",
      priceTenths: 50 + squadPosition,
      code: 900_000 + squadPosition,
    },
    ...extra,
  };
}

function squad(shape: [number, number, number]): PublicTeamPick[] {
  const [defenders, midfielders, forwards] = shape;
  const starters: PublicTeamPick[] = [pick(1, "GKP", 1)];
  let slot = 2;
  for (let index = 0; index < defenders; index += 1)
    starters.push(pick(slot++, "DEF", 1));
  for (let index = 0; index < midfielders; index += 1)
    starters.push(pick(slot++, "MID", 1));
  for (let index = 0; index < forwards; index += 1)
    starters.push(pick(slot++, "FWD", 1));
  const bench: PublicTeamPick[] = [
    pick(12, "GKP", 0),
    pick(13, "DEF", 0),
    pick(14, "MID", 0),
    pick(15, "FWD", 0),
  ];
  return [...starters, ...bench];
}

describe("PitchView", () => {
  it.each([
    [[3, 4, 3], "3-4-3"],
    [[4, 4, 2], "4-4-2"],
    [[5, 4, 1], "5-4-1"],
    [[3, 5, 2], "3-5-2"],
    [[5, 2, 3], "5-2-3"],
  ] as const)("lays out %s as %s", (shape, expected) => {
    render(<PitchView picks={squad([...shape] as [number, number, number])} />);

    expect(screen.getByText(expected)).toBeInTheDocument();
    expect(
      within(screen.getByRole("list", { name: "Defenders" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(shape[0]);
    expect(
      within(screen.getByRole("list", { name: "Midfielders" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(shape[1]);
    expect(
      within(screen.getByRole("list", { name: "Forwards" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(shape[2]);
  });

  it("keeps the bench in submission order and off the pitch", () => {
    render(<PitchView picks={squad([4, 4, 2])} />);

    const bench = screen.getByRole("list", { name: "Substitutes in order" });
    expect(within(bench).getAllByRole("listitem")).toHaveLength(4);
    expect(
      within(screen.getByRole("list", { name: "Goalkeeper" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(1);
  });

  it("names the armbands in text, not colour alone", () => {
    const picks = squad([4, 4, 2]).map((entry) =>
      entry.squadPosition === 7
        ? { ...entry, isCaptain: true, multiplier: 2 }
        : entry.squadPosition === 8
          ? { ...entry, isViceCaptain: true }
          : entry,
    );
    render(<PitchView picks={picks} />);

    expect(screen.getByText("Captain, 2×")).toBeInTheDocument();
    expect(screen.getByText("Vice-captain")).toBeInTheDocument();
  });

  it("shows an unresolved pick without inventing a position", () => {
    const picks = squad([4, 4, 2]).map((entry) =>
      entry.squadPosition === 11 ? { ...entry, identity: null } : entry,
    );
    render(<PitchView picks={picks} />);

    expect(screen.getByText("#111")).toBeInTheDocument();
    expect(screen.getByText("formation unavailable")).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Unresolved starters" }),
    ).toBeInTheDocument();
  });
});
