import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import validation from "../data/xstart-validation.json";
import { XStartCalibration } from "./XStartCalibration";

describe("XStartCalibration", () => {
  it("shows the shipped field's reliability failure and every club as a bar", () => {
    render(<XStartCalibration />);

    expect(
      screen.getByRole("heading", { name: "How close was the predicted XI?" }),
    ).toBeVisible();
    const highest = screen.getByText("0.9-1.0").closest('[role="listitem"]');
    expect(highest).not.toBeNull();
    expect(highest).toHaveTextContent("92% / 68%");
    expect(highest).toHaveTextContent("n=28");
    for (const club of validation.clubs) {
      expect(
        screen.getByRole("button", { name: new RegExp(`^${club.club}`) }),
      ).toHaveTextContent(`${String(club.topElevenHits)}/11`);
    }
  });

  it("filters a club out of both charts when unticked", () => {
    render(<XStartCalibration />);
    const first = validation.clubs[0]!;

    fireEvent.click(screen.getByRole("checkbox", { name: first.club }));

    expect(
      screen.queryByRole("button", { name: new RegExp(`^${first.club}`) }),
    ).not.toBeInTheDocument();
  });

  it("opens the predicted-versus-actual XI on a club's bar", () => {
    render(<XStartCalibration />);
    const club = validation.clubs.find((entry) => entry.selected.length > 0)!;

    fireEvent.click(
      screen.getByRole("button", {
        name: new RegExp(`^${club.club}`),
      }),
    );

    const popup = screen.getByRole("dialog", {
      name: `${club.club} xStart check`,
    });
    expect(within(popup).getByText("Predicted XI")).toBeVisible();
    expect(within(popup).getByText("Actual XI")).toBeVisible();
  });
});
