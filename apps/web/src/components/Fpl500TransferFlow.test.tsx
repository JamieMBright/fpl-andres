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
  });
});
