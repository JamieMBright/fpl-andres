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

  it("shows the full latest per-gameweek row from FPL", async () => {
    showModalPolyfill();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation((input) => {
        const url = String(input);
        if (url.includes("fixtures")) return Promise.resolve(Response.json([]));
        if (url.includes("element-summary")) {
          return Promise.resolve(
            Response.json({
              history: [
                {
                  event: null,
                  round: 3,
                  fixture: 25,
                  kickoff_time: "2026-09-05T14:00:00Z",
                  minutes: 84,
                  total_points: 2,
                  goals_scored: 0,
                  assists: 0,
                  clean_sheets: 1,
                  goals_conceded: 0,
                  own_goals: 0,
                  penalties_saved: 0,
                  penalties_missed: 0,
                  yellow_cards: 0,
                  red_cards: 0,
                  saves: 0,
                  bonus: 0,
                  bps: 10,
                  influence: "1.2",
                  creativity: "17.5",
                  threat: "20.0",
                  ict_index: "3.9",
                  starts: 1,
                  expected_goals: "0.24",
                  expected_assists: "0.44",
                  expected_goal_involvements: "0.68",
                  expected_goals_conceded: "0.22",
                  defensive_contribution: 2,
                },
              ],
            }),
          );
        }
        return Promise.resolve(
          Response.json({
            events: [{ id: 4, deadline_time: "2026-09-12T12:30:00Z" }],
            element_types: [{ id: 4, singular_name_short: "FWD" }],
            teams: [
              { id: 2, code: 14, short_name: "AVL", name: "Aston Villa" },
            ],
            elements: [
              {
                id: 166,
                code: 999_997,
                web_name: "N.Jackson",
                element_type: 4,
                team: 2,
                now_cost: 65,
                status: "a",
                total_points: 10,
                event_points: 2,
              },
            ],
          }),
        );
      }),
    );

    render(
      <PlayerDetail
        onClose={() => undefined}
        player={{
          code: 999_997,
          name: "N.Jackson",
          position: "FWD",
          club: "AVL",
          priceTenths: 65,
        }}
      />,
    );

    const dialog = screen.getByRole("dialog");
    expect(
      await within(dialog).findByRole("heading", { name: "Recent gameweeks" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("GW3")).toBeInTheDocument();
    expect(within(dialog).getByText("84")).toBeInTheDocument();
    expect(within(dialog).getByText("0.24")).toBeInTheDocument();
    expect(
      within(within(dialog).getByRole("row", { name: /GW3/ })).getAllByText(
        "2",
      ),
    ).toHaveLength(2);
  });
});
