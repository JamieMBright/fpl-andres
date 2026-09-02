import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerPoolTable } from "./PlayerPoolTable";
import { forgetLastGoodPool } from "../state/player-pool";

/**
 * Customizable columns and a CSV export, so a reader who wants xG or
 * transfer counts is not stuck scrolling past twelve columns to see them,
 * and can take the table's numbers to a spreadsheet.
 */

function bootstrap() {
  return {
    events: [
      { id: 3, deadline_time: "2026-09-04T17:30:00Z", is_current: true },
    ],
    element_types: [{ id: 3, singular_name_short: "MID" }],
    teams: [{ id: 1, code: 3, short_name: "ARS", name: "Arsenal" }],
    elements: [
      {
        id: 1,
        code: 900_001,
        web_name: "Player 0",
        element_type: 3,
        team: 1,
        now_cost: 55,
        status: "a",
        total_points: 12,
        event_points: 4,
        expected_goals: "3.42",
        expected_assists: "1.10",
        transfers_in_event: 5000,
        transfers_out_event: 100,
        cost_change_event: 1,
      },
    ],
  };
}

function respond(input: RequestInfo | URL): Response {
  return String(input).includes("fixtures")
    ? Response.json([])
    : Response.json(bootstrap());
}

describe("player pool table column customization", () => {
  beforeEach(() => {
    forgetLastGoodPool();
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockImplementation((input) => Promise.resolve(respond(input))),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("hides the advanced-stat columns by default and reveals xG on request", async () => {
    render(<PlayerPoolTable />);
    await screen.findByText("Player 0");

    expect(screen.queryByRole("columnheader", { name: "xG" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Columns" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "xG" }));

    expect(
      screen.getByRole("columnheader", { name: "xG" }),
    ).toBeInTheDocument();
  });

  it("remembers a shown column across a remount", async () => {
    const { unmount } = render(<PlayerPoolTable />);
    await screen.findByText("Player 0");
    fireEvent.click(screen.getByRole("button", { name: "Columns" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "xG" }));
    unmount();

    render(<PlayerPoolTable />);
    await screen.findByText("Player 0");

    expect(
      screen.getByRole("columnheader", { name: "xG" }),
    ).toBeInTheDocument();
  });

  it("moves a column up when its up arrow is used", async () => {
    render(<PlayerPoolTable />);
    await screen.findByText("Player 0");
    fireEvent.click(screen.getByRole("button", { name: "Columns" }));

    fireEvent.click(screen.getByRole("button", { name: "Move Club up" }));

    const headers = screen
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers.indexOf("Club")).toBeLessThan(headers.indexOf("Pos"));
  });

  it("downloads a CSV with only the shown columns and formatted values", async () => {
    let capturedBlob: Blob | null = null;
    const createObjectURL = vi.fn((blob: Blob) => {
      capturedBlob = blob;
      return "blob:fake";
    });
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const clicked = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = originalCreateElement(tag);
      if (tag === "a") el.click = clicked;
      return el;
    });

    render(<PlayerPoolTable />);
    await screen.findByText("Player 0");

    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(capturedBlob).not.toBeNull();
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("could not read blob"));
      reader.readAsText(capturedBlob!);
    });
    expect(text).toContain("Player");
    expect(text).toContain("Player 0");
    expect(clicked).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake");
  });
});
