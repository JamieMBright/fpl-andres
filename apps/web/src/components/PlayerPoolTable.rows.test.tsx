import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerPoolTable } from "./PlayerPoolTable";
import { forgetLastGoodPool } from "../state/player-pool";

/**
 * Two things the players tab was missing: FPL's own live scoring, and a way
 * to see more than a fixed page of rows without narrowing every filter.
 */

function bootstrap(rows: number) {
  return {
    events: [{ id: 1, deadline_time: "2026-08-21T17:30:00Z" }],
    element_types: [{ id: 3, singular_name_short: "MID" }],
    teams: [{ id: 1, code: 3, short_name: "ARS", name: "Arsenal" }],
    elements: Array.from({ length: rows }, (_, index) => ({
      id: index + 1,
      code: 900_000 + index,
      web_name: `Player ${String(index)}`,
      element_type: 3,
      team: 1,
      now_cost: 55,
      status: "a",
      total_points: index,
      event_points: index % 12,
    })),
  };
}

function respond(input: RequestInfo | URL, rows: number): Response {
  return String(input).includes("fixtures")
    ? Response.json([])
    : Response.json(bootstrap(rows));
}

describe("player pool table live points and row limit", () => {
  beforeEach(() => {
    forgetLastGoodPool();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows FPL's own season and gameweek points instead of a dash", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockImplementation((input) => Promise.resolve(respond(input, 1))),
    );

    render(<PlayerPoolTable />);

    expect(await screen.findByText("Player 0")).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /GW Pts/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /Total Pts/ }),
    ).toBeInTheDocument();
  });

  it("defaults to showing 25 rows and can be widened to all", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockImplementation((input) => Promise.resolve(respond(input, 40))),
    );

    render(<PlayerPoolTable />);

    await screen.findByText("Player 0");
    expect(document.querySelectorAll("tbody tr")).toHaveLength(25);
    expect(screen.getByText(/Showing the first 25 of 40/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Show"), {
      target: { value: "all" },
    });

    expect(document.querySelectorAll("tbody tr")).toHaveLength(40);
    expect(screen.queryByText(/Showing the first/)).toBeNull();
  });
});
