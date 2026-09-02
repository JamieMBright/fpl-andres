import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { XStartCalibration } from "./XStartCalibration";
import validation from "../data/xstart-validation.json";

const latest = validation.events.at(-1)!;

describe("XStartCalibration", () => {
  it("draws one cumulative kit-coloured line per club", () => {
    const { container } = render(<XStartCalibration />);

    expect(
      screen.getByRole("heading", { name: "How close was the predicted XI?" }),
    ).toBeVisible();
    expect(container.querySelectorAll(".xstart-cumulative-line")).toHaveLength(
      20,
    );
    expect(screen.getByRole("combobox", { name: "Gameweek" })).toHaveValue(
      String(latest.event),
    );
    expect(screen.queryByText("0.9-1.0")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("filters a club out of the line and both bar views", () => {
    const { container } = render(<XStartCalibration />);
    const first = latest.clubs[0]!;

    fireEvent.click(screen.getByRole("checkbox", { name: first.club }));

    expect(
      container.querySelector(
        `.xstart-cumulative-line[data-club="${first.club}"]`,
      ),
    ).toBeNull();
    expect(
      screen.queryByRole("button", {
        name: new RegExp(`^About ${first.club} .*xStart detail$`),
      }),
    ).not.toBeInTheDocument();
  });

  it("selects the last-gameweek bars and exposes concise detail", () => {
    render(<XStartCalibration />);
    const firstEvent = validation.events[0]!;
    const club = firstEvent.clubs[0]!;

    fireEvent.change(screen.getByRole("combobox", { name: "Gameweek" }), {
      target: { value: String(firstEvent.event) },
    });
    expect(
      screen.getByRole("heading", { name: `GW${firstEvent.event} hits` }),
    ).toBeVisible();

    const detail = screen.getByRole("button", {
      name: `About ${club.club} GW${firstEvent.event} xStart detail`,
    });
    fireEvent.focus(detail);
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent(`${club.count} predictions`);
    expect(tooltip).toHaveTextContent(`${club.actualStarters} actual starters`);
    expect(tooltip).toHaveTextContent(`${club.topElevenHits}/11 hits`);
    expect(tooltip).toHaveTextContent("Starters left out");
  });
});
