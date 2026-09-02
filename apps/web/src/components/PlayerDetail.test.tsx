import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { percent } from "../format";
import { forgetLastGoodPool } from "../state/player-pool";
import { allProjections, projectionSeason } from "../state/squad-projection";
import { PlayerDetail } from "./PlayerDetail";

beforeEach(() => {
  forgetLastGoodPool();
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>().mockImplementation((input) =>
      Promise.resolve(
        String(input).includes("fixtures")
          ? Response.json([])
          : Response.json({
              events: [],
              element_types: [],
              teams: [],
              elements: [],
            }),
      ),
    ),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PlayerDetail minutes bridge", () => {
  it("keeps true starts separate from reaching 60 minutes", () => {
    const player = allProjections()[0];
    expect(player).toBeDefined();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = vi.fn(function showModal(
        this: HTMLDialogElement,
      ) {
        this.setAttribute("open", "");
      });
    }

    render(
      <PlayerDetail
        onClose={() => undefined}
        player={{
          code: player!.code,
          name: player!.name,
          position: player!.position,
          club: "ARS",
          priceTenths: player!.priceTenths ?? 0,
        }}
      />,
    );

    // The card defaults to this season; these are last season's figures.
    fireEvent.click(screen.getByRole("radio", { name: projectionSeason }));

    const starts = screen.getByText("Starts").closest("div");
    const sixty = screen.getByText("Reaches 60").closest("div");
    expect(starts).not.toBeNull();
    expect(sixty).not.toBeNull();
    expect(within(starts!).getByRole("term")).toHaveTextContent("Starts");
    expect(starts).toHaveTextContent(
      player!.probabilityStartModel === undefined
        ? "—"
        : percent.format(player!.probabilityStartModel),
    );
    expect(sixty).toHaveTextContent(
      percent.format(
        player!.probabilitySixtyMinutes ?? player!.probabilityStart,
      ),
    );
  });
});

function showModalPolyfill(): void {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = vi.fn(function showModal(
      this: HTMLDialogElement,
    ) {
      this.setAttribute("open", "");
    });
  }
}

describe("PlayerDetail season split", () => {
  it("defaults to this season, and shows a new signing's live points there", () => {
    showModalPolyfill();

    render(
      <PlayerDetail
        onClose={() => undefined}
        player={{
          code: 999_999,
          name: "New Signing",
          position: "MID",
          club: "MCI",
          priceTenths: 75,
          seasonPoints: 12,
          lastGameweekPoints: 5,
        }}
      />,
    );

    expect(screen.getByRole("radio", { name: "This season" })).toBeChecked();
    expect(screen.getByText("Points this season")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(
      screen.queryByText(/no Premier League record/),
    ).not.toBeInTheDocument();
  });

  it("says so when FPL has no live row for the player", async () => {
    showModalPolyfill();

    render(
      <PlayerDetail
        onClose={() => undefined}
        player={{
          code: 999_998,
          name: "No Live Data",
          position: "MID",
          club: "MCI",
          priceTenths: 75,
        }}
      />,
    );

    expect(
      await screen.findByText(/FPL did not supply live stats for this player/),
    ).toBeInTheDocument();
  });
});
