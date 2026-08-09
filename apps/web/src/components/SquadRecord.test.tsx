import type { PublicTeamPick } from "@fpl-andres/contracts";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SquadRecord } from "./SquadRecord";
import { projectionFor } from "../state/squad-projection";

// Bruno Fernandes, whose record is in the published artifact. What the record
// says moves every time the artifact is refreshed, so it is read rather than
// typed: the claim under test is the join, not the number.
const KNOWN_CODE = 141746;

function pick(squadPosition: number, code: number | null): PublicTeamPick {
  return {
    elementId: 100 + squadPosition,
    squadPosition,
    multiplier: squadPosition <= 11 ? 1 : 0,
    isCaptain: false,
    isViceCaptain: false,
    identity:
      code === null
        ? null
        : {
            webName: `Player ${squadPosition}`,
            positionCode: "MID",
            teamShortName: "TST",
            priceTenths: 50,
            code,
          },
  };
}

describe("SquadRecord", () => {
  it("shows the published per-match record for a known player", () => {
    const published = projectionFor(KNOWN_CODE);
    render(<SquadRecord picks={[pick(1, KNOWN_CODE)]} />);

    expect(
      screen.getByRole("table", { name: /last season record/i }),
    ).toBeInTheDocument();
    expect(published).not.toBeNull();
    expect(
      screen.getByText(published!.expectedPoints.toFixed(2)),
    ).toBeInTheDocument();
  });

  it("names the players it has no record for rather than inventing one", () => {
    render(<SquadRecord picks={[pick(1, KNOWN_CODE), pick(2, null)]} />);

    expect(screen.getByText(/no record for 1/i)).toBeInTheDocument();
    expect(screen.getByText(/FPL element 102/)).toBeInTheDocument();
  });

  it("withholds a squad total while any player is unaccounted for", () => {
    render(<SquadRecord picks={[pick(1, KNOWN_CODE), pick(2, null)]} />);

    expect(screen.queryByText(/strongest eleven/i)).not.toBeInTheDocument();
  });

  it("totals the strongest eleven once every player is known", () => {
    const picks = Array.from({ length: 15 }, (_, index) =>
      pick(index + 1, KNOWN_CODE),
    );

    render(<SquadRecord picks={picks} />);

    expect(screen.getByText(/strongest eleven/i)).toBeInTheDocument();
  });

  it("says so plainly when it knows nobody in the squad", () => {
    render(<SquadRecord picks={[pick(1, null)]} />);

    expect(
      screen.getByText(/hold no premier league record/i),
    ).toBeInTheDocument();
  });
});
