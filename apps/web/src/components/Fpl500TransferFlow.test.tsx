import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Fpl500TransferFlow } from "./Fpl500TransferFlow";

const SERIES = {
  events: [1, 2],
  samples: { "01": { counted: 100 }, "02": { counted: 100 } },
  holdings: {
    "01": [
      { elementId: 1, ownedShare: 0.1, name: "Big riser" },
      { elementId: 2, ownedShare: 0.3, name: "One out" },
    ],
    "02": [
      { elementId: 1, ownedShare: 0.4, name: "Big riser" },
      { elementId: 2, ownedShare: 0.29, name: "One out" },
    ],
  },
};

describe("Fpl500TransferFlow", () => {
  it("says there is nothing to compare with one captured gameweek", () => {
    render(
      <Fpl500TransferFlow
        series={{
          events: [1],
          samples: { "01": { counted: 100 } },
          holdings: {},
        }}
      />,
    );

    expect(
      screen.getByText(/needs a second to compare it to/i),
    ).toBeInTheDocument();
  });

  it("filters out a player below the minimum-transfers slider", () => {
    render(<Fpl500TransferFlow series={SERIES} />);

    expect(screen.getByLabelText(/minimum transfers/i)).toHaveValue("5");
    expect(screen.getByText("Big riser")).toBeInTheDocument();
    expect(screen.queryByText("One out")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/minimum transfers/i), {
      target: { value: "0" },
    });

    expect(screen.getByText("One out")).toBeInTheDocument();
  });

  it("labels a window of one as the last gameweek", () => {
    render(<Fpl500TransferFlow series={SERIES} />);

    expect(screen.getByText("Last GW")).toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: /gameweeks/i })).toBeNull();
    expect(
      screen.getByRole("region", { name: "Scrollable transfer flow" }),
    ).toBeInTheDocument();
  });

  it("keeps every qualifying move in a bounded result and restores the window slider", () => {
    const holdings = Array.from({ length: 60 }, (_, index) => ({
      elementId: index + 1,
      ownedShare: 0.1,
      name: `Player ${String(index + 1)}`,
    }));
    render(
      <Fpl500TransferFlow
        series={{
          events: [1, 2, 3],
          samples: {
            "01": { counted: 100 },
            "02": { counted: 100 },
            "03": { counted: 100 },
          },
          holdings: {
            "01": holdings,
            "02": holdings.map((row) => ({ ...row, ownedShare: 0.2 })),
            "03": holdings.map((row) => ({ ...row, ownedShare: 0.3 })),
          },
        }}
      />,
    );

    expect(
      screen.getByRole("slider", { name: /gameweeks/i }),
    ).toBeInTheDocument();
    const region = screen.getByRole("region", {
      name: "Scrollable transfer flow",
    });
    expect(region.querySelectorAll(".fpl500-transfer-row")).toHaveLength(60);
  });
});
