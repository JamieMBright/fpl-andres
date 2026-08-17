import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { TopPicks } from "./TopPicks";
import { DEFAULT_HORIZON, horizonPointsByCode } from "../state/horizon-points";
import { SEASON_PLAYERS } from "../state/season-solver";

/**
 * The claim on the card is "best five-gameweek value at this position". These
 * check the rendered order against xPts5 per million, because cards that show
 * raw xPts5 while quietly ranking on it would otherwise still look plausible.
 */

function best(position: string): { name: string; points: number } {
  return topThree(position)[0]!;
}

function topThree(
  position: string,
): { code: number; name: string; points: number; value: number }[] {
  const totals = horizonPointsByCode(DEFAULT_HORIZON);
  return SEASON_PLAYERS.filter((player) => player.position === position)
    .flatMap((player) => {
      const points = totals.get(player.code);
      return points === undefined
        ? []
        : [
            {
              code: player.code,
              name: player.name,
              points,
              value: points / (player.priceTenths / 10),
            },
          ];
    })
    .sort((left, right) => right.value - left.value || left.code - right.code)
    .slice(0, 3);
}

describe("TopPicks", () => {
  // jsdom implements the element but not the method the profile opens with.
  beforeAll(() => {
    HTMLDialogElement.prototype.showModal = function open() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function shut() {
      this.open = false;
    };
  });

  it("names three players per position in xPts5 per million order", () => {
    const { container } = render(<TopPicks />);

    expect(container.querySelectorAll(".top-pick-column")).toHaveLength(4);
    expect(container.querySelectorAll(".top-pick-hero")).toHaveLength(4);
    for (const position of ["GKP", "DEF", "MID", "FWD"]) {
      expect(
        container.querySelectorAll(`[data-position="${position}"]`),
      ).toHaveLength(1);
    }
    expect(container.querySelectorAll(".top-pick-runners > li")).toHaveLength(
      8,
    );
    for (const role of ["Goalkeeper", "Defender", "Midfielder", "Forward"]) {
      expect(screen.getByText(role)).toBeInTheDocument();
    }
    for (const position of ["GKP", "DEF", "MID", "FWD"]) {
      const expected = topThree(position);
      const column = container.querySelector(`[data-position="${position}"]`);
      expect(column).not.toBeNull();
      expect(
        [
          ...column!.querySelectorAll(
            ".top-pick-name button, .top-pick-runner-name",
          ),
        ].map((button) => button.textContent),
      ).toEqual(expected.map(({ name }) => name));
      for (const { name, points } of expected) {
        expect(screen.getByRole("button", { name })).toBeInTheDocument();
        expect(
          screen.getAllByText(new RegExp(points.toFixed(1))).length,
        ).toBeGreaterThan(0);
      }
    }
  });

  it("picks the highest five-gameweek value, not the highest raw projection", () => {
    render(<TopPicks />);

    for (const position of ["GKP", "DEF", "MID", "FWD"]) {
      const { name, points } = best(position);
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
      expect(
        screen.getAllByText(points.toFixed(1)).length,
      ).toBeGreaterThanOrEqual(1);
    }
  });

  it("keeps the fixture breakdown shut until it is asked for", () => {
    const { container } = render(<TopPicks />);

    const panel = container.querySelector(".top-pick-panel");
    expect(panel).toHaveAttribute("hidden");
  });

  it("opens the breakdown from the keyboard, not only under a pointer", () => {
    render(<TopPicks />);
    const [trigger] = screen.getAllByRole("button", { name: /xPts5$/ });

    fireEvent.focus(trigger!);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("shows only the breakdown for the card that was asked about", async () => {
    render(<TopPicks />);
    const triggers = screen.getAllByRole("button", { name: /xPts5$/ });
    await userEvent.click(triggers[2]!);

    expect(triggers[0]).toHaveAttribute("aria-expanded", "false");
    expect(triggers[2]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(new RegExp(best("MID").name))).toBeInTheDocument();
  });

  it("shows one column per gameweek in the horizon, with the venue in words", async () => {
    render(<TopPicks />);
    const [trigger] = screen.getAllByRole("button", { name: /xPts5$/ });
    await userEvent.click(trigger!);

    const panel = document.getElementById(
      trigger!.getAttribute("aria-controls")!,
    );
    expect(panel).not.toBeNull();
    expect(panel!.querySelectorAll(".top-pick-fixture")).toHaveLength(
      DEFAULT_HORIZON,
    );
    // Home or away is only recorded in the published opponent string, so a
    // breakdown that lost it would still look complete.
    expect(within(panel!).getAllByText(/^(home|away)$/).length).toBeGreaterThan(
      0,
    );
  });

  it("opens the player's own profile from the name", async () => {
    render(<TopPicks />);
    const { name } = best("MID");

    await userEvent.click(screen.getByRole("button", { name }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("opens a runner's profile without opening a fixture panel", async () => {
    const { container } = render(<TopPicks />);
    const runner = topThree("FWD")[1];
    expect(runner).toBeDefined();

    await userEvent.click(screen.getByRole("button", { name: runner!.name }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(container.querySelector(".top-pick-panel")).toHaveAttribute(
      "hidden",
    );
  });

  it("gives every rank marker an accessible name", () => {
    render(<TopPicks />);

    expect(screen.getAllByRole("img", { name: "Rank 1" })).toHaveLength(4);
    expect(screen.getAllByRole("img", { name: "Rank 2" })).toHaveLength(4);
    expect(screen.getAllByRole("img", { name: "Rank 3" })).toHaveLength(4);
  });
});
