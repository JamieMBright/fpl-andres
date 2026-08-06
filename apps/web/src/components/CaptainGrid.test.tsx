import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CaptainGrid, type SeasonPicks } from "./CaptainGrid";

/**
 * The grid is an index into two lookup tables, so it can be wrong quietly.
 *
 * A cell pointing at the wrong player, or a column that closes up where a
 * method named nobody, still renders a plausible-looking grid. These pin the
 * alignment and the things a reader would otherwise have to trust.
 */

const SEASON: SeasonPicks = {
  season: "2024-25",
  gameweeks: [1, 2, 3],
  clubs: { "14": "LIV", "43": "MCI" },
  players: { "1": ["Salah", 14], "2": ["Haaland", 43] },
  ceiling: [17, 13, null],
  rows: [
    {
      group: "method",
      label: "model",
      picks: [
        [1, 12, "BOU"],
        [2, 2, "ars"],
        [1, 6, ""],
      ],
    },
    { group: "thesis", label: "form", picks: [null, [1, 10, "ars"], null] },
  ],
};

const EARLIER: SeasonPicks = {
  ...SEASON,
  season: "2023-24",
  rows: [
    { group: "method", label: "model", picks: [[2, 4, "EVE"], null, null] },
  ],
};

describe("CaptainGrid", () => {
  it("renders one row per method and one column per gameweek", () => {
    render(<CaptainGrid seasons={[SEASON]} />);
    expect(screen.getByRole("row", { name: /model/ })).toBeTruthy();
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
  });

  it("keeps a gameweek a method skipped as a hole, not a shift", () => {
    // The failure that matters: closing the gap would slide gameweek 2 into
    // gameweek 1's column for that row and misname every week after it.
    const { container } = render(<CaptainGrid seasons={[SEASON]} />);
    const rows = container.querySelectorAll("tbody tr");
    const form = rows[1]?.querySelectorAll("td");
    expect(form).toHaveLength(3);
    expect(form?.[0]?.className).toContain("captain-grid-empty");
    expect(form?.[1]?.textContent).toContain("Salah");
  });

  it("names the player rather than printing his element id", () => {
    render(<CaptainGrid seasons={[SEASON]} />);
    expect(screen.getAllByText("Haaland").length).toBeGreaterThan(0);
  });

  it("prints the opponent exactly as given, because the casing is the venue", () => {
    // Upper is home and lower is away. Any re-casing here silently reverses it.
    const { container } = render(<CaptainGrid seasons={[SEASON]} />);
    const against = [
      ...container.querySelectorAll(".captain-grid-against"),
    ].map((node) => node.textContent);
    expect(against).toContain("BOU");
    expect(against).toContain("ars");
  });

  it("shows a dash where a player had no fixture at all", () => {
    const { container } = render(<CaptainGrid seasons={[SEASON]} />);
    const against = [
      ...container.querySelectorAll(".captain-grid-against"),
    ].map((node) => node.textContent);
    expect(against).toContain("—");
  });

  it("marks a blank and a haul with more than colour", () => {
    const { container } = render(<CaptainGrid seasons={[SEASON]} />);
    expect(container.querySelectorAll(".captain-grid-blank")).toHaveLength(1);
    expect(container.querySelectorAll(".captain-grid-haul")).toHaveLength(2);
  });

  it("carries the week's ceiling so a haul can be read against it", () => {
    render(<CaptainGrid seasons={[SEASON]} />);
    expect(screen.getByText("17")).toBeTruthy();
  });

  it("opens on the most recent season and switches on demand", async () => {
    render(<CaptainGrid seasons={[EARLIER, SEASON]} />);
    expect(
      screen
        .getByRole("button", { name: "2024-25" })
        .getAttribute("aria-pressed"),
    ).toBe("true");

    await userEvent.click(screen.getByRole("button", { name: "2023-24" }));
    expect(screen.getAllByText("Haaland").length).toBeGreaterThan(0);
    expect(screen.queryByText("Salah")).toBeNull();
  });

  it("marks this project's own row so the eye finds it among fourteen", () => {
    const { container } = render(
      <CaptainGrid mine={["model"]} seasons={[SEASON]} />,
    );
    expect(container.querySelectorAll(".captain-grid-mine")).toHaveLength(1);
  });

  it("renders both rows when a label names a method and a thesis alike", () => {
    // `components` is one of each. Keyed on the label alone React drops one and
    // the grid shows thirteen rows while the artifact holds fourteen.
    const clash: SeasonPicks = {
      ...SEASON,
      rows: [
        {
          group: "method",
          label: "components",
          picks: [[1, 3, "BOU"], null, null],
        },
        {
          group: "thesis",
          label: "components",
          picks: [[2, 9, "BOU"], null, null],
        },
      ],
    };
    const { container } = render(<CaptainGrid seasons={[clash]} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
  });

  it("says the artifact predates the record rather than drawing an empty axis", () => {
    const { container } = render(<CaptainGrid seasons={[]} />);
    expect(container.querySelector("table")).toBeNull();
    expect(container.textContent).toContain("predates");
  });

  it("skips a season the backtest scored nothing in", () => {
    const empty: SeasonPicks = {
      ...SEASON,
      season: "2019-20",
      gameweeks: [],
      rows: [],
    };
    render(<CaptainGrid seasons={[empty, SEASON]} />);
    expect(screen.queryByRole("button", { name: "2019-20" })).toBeNull();
  });

  it("is a labelled scrollable region, so it can be reached by keyboard", () => {
    const { container } = render(<CaptainGrid seasons={[SEASON]} />);
    const region = container.querySelector('[role="region"]');
    expect(region?.getAttribute("tabindex")).toBe("0");
    expect(region?.getAttribute("aria-label")).toContain("Scrollable");
  });
});

describe("CaptainGrid reasoning", () => {
  const WITH_MATHS: SeasonPicks = {
    ...SEASON,
    maths: [
      {
        // Element 2 projects highest; element 1 was picked anyway. This is the
        // shape of the real question -- why him and not the obvious one.
        "1": [6.2, 5.9, 4.0, 0.95, 40, 11.0, 1.3],
        "2": [5.9, 5.7, 7.0, 0.98, 95, 14.0, 0.9],
      },
      {},
      {},
    ],
  };

  it("says nothing until a pick is pointed at", () => {
    const { container } = render(<CaptainGrid seasons={[WITH_MATHS]} />);
    expect(
      container.querySelector(".captain-grid-readout-idle"),
    ).not.toBeNull();
  });

  it("explains a pick on hover", async () => {
    render(<CaptainGrid seasons={[WITH_MATHS]} />);
    await userEvent.hover(screen.getAllByRole("button", { name: /Salah/ })[0]!);
    expect(screen.getByText(/Gameweek 1/)).toBeTruthy();
  });

  it("explains the same pick on keyboard focus, not only on hover", async () => {
    // Hover alone would put the reasoning out of reach of touch and keyboard.
    render(<CaptainGrid seasons={[WITH_MATHS]} />);
    fireEvent.focus(screen.getAllByRole("button", { name: /Salah/ })[0]!);
    expect(screen.getByText(/Gameweek 1/)).toBeTruthy();
  });

  it("shows what the pick was chosen over, ranked by projection", async () => {
    const { container } = render(<CaptainGrid seasons={[WITH_MATHS]} />);
    await userEvent.hover(screen.getAllByRole("button", { name: /Salah/ })[0]!);
    const rows = [
      ...container.querySelectorAll(".captain-grid-readout tbody tr"),
    ].map((node) => node.querySelector("th")?.textContent);
    expect(rows[0]).toContain("Salah");
    expect(rows[1]).toContain("Haaland");
  });

  it("marks which candidate was chosen", async () => {
    const { container } = render(<CaptainGrid seasons={[WITH_MATHS]} />);
    await userEvent.hover(screen.getAllByRole("button", { name: /Salah/ })[0]!);
    const chosen = container.querySelectorAll(".captain-grid-chosen");
    expect(chosen).toHaveLength(1);
    expect(chosen[0]?.textContent).toContain("Salah");
  });

  it("says the artifact predates the arithmetic rather than inventing it", async () => {
    render(<CaptainGrid seasons={[SEASON]} />);
    await userEvent.hover(screen.getAllByRole("button", { name: /Salah/ })[0]!);
    expect(screen.getByText(/predates the published arithmetic/)).toBeTruthy();
  });

  it("clears the reasoning when the season changes", async () => {
    render(<CaptainGrid seasons={[EARLIER, WITH_MATHS]} />);
    await userEvent.hover(screen.getAllByRole("button", { name: /Salah/ })[0]!);
    expect(screen.queryByText(/Gameweek 1 —/)).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "2023-24" }));
    expect(screen.queryByText(/Gameweek 1 —/)).toBeNull();
  });
});
