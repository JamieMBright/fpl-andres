import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
    expect(
      screen.getByRole("combobox", { name: "Performance period" }),
    ).toHaveValue("average");
    expect(screen.queryByText("0.9-1.0")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("filters a club out of the line and combined bar view", () => {
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

  it("combines season average and gameweeks in one bar view", () => {
    render(<XStartCalibration />);
    const firstEvent = validation.events[0]!;
    const club = firstEvent.clubs[0]!;

    const period = screen.getByRole("combobox", { name: "Performance period" });
    expect(
      Array.from(
        period.querySelectorAll("option"),
        (option) => option.textContent,
      ),
    ).toEqual([
      "Season average",
      ...validation.events.map((event) => `GW${event.event}`),
    ]);
    expect(period).toHaveValue("average");
    expect(
      screen.getAllByRole("list", { name: "xStart performance by club" }),
    ).toHaveLength(1);
    const seasonAverage =
      validation.events.reduce(
        (total, event) =>
          total +
          event.clubs.find((entry) => entry.club === club.club)!.topElevenHits,
        0,
      ) / validation.events.length;
    const clubRow = screen
      .getByText(club.club, { selector: ".xstart-score-bar-label" })
      .closest("li");
    expect(clubRow).not.toBeNull();
    expect(
      within(clubRow!).getByText(`${seasonAverage.toFixed(1)}/11`),
    ).toBeInTheDocument();

    fireEvent.change(period, {
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

  it("orders the combined bars by club, easiest or hardest", () => {
    const { container } = render(<XStartCalibration />);
    const order = screen.getByRole("combobox", { name: "Sort performance" });
    expect(
      Array.from(
        order.querySelectorAll("option"),
        (option) => option.textContent,
      ),
    ).toEqual(["Club", "Easiest to predict", "Hardest to predict"]);

    const labels = () =>
      Array.from(
        container.querySelectorAll(
          ".xstart-performance-bars .xstart-score-bar-label",
        ),
        (label) => label.textContent,
      );
    const alphabetical = [...labels()].sort((left, right) =>
      (left ?? "").localeCompare(right ?? ""),
    );
    expect(labels()).toEqual(alphabetical);

    fireEvent.change(order, { target: { value: "easiest" } });
    const easiestValues = Array.from(
      container.querySelectorAll(".xstart-performance-bars li"),
      (row) => Number(row.getAttribute("data-score")),
    );
    expect(easiestValues).toEqual([...easiestValues].sort((a, b) => b - a));

    fireEvent.change(order, { target: { value: "hardest" } });
    const hardestValues = Array.from(
      container.querySelectorAll(".xstart-performance-bars li"),
      (row) => Number(row.getAttribute("data-score")),
    );
    expect(hardestValues).toEqual([...hardestValues].sort((a, b) => a - b));
  });

  it("snaps line hover to the nearest gameweek and names the club score", () => {
    const { container } = render(<XStartCalibration />);
    const club = latest.clubs[0]!;
    const hitArea = container.querySelector(
      `.xstart-cumulative-hit-area[data-club="${club.club}"]`,
    );
    const svg = container.querySelector(".xstart-cumulative-chart svg");
    expect(hitArea).not.toBeNull();
    expect(svg).not.toBeNull();
    vi.spyOn(svg!, "getBoundingClientRect").mockReturnValue({
      bottom: 260,
      height: 260,
      left: 0,
      right: 640,
      top: 0,
      width: 640,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    fireEvent.pointerMove(hitArea!, { clientX: 500, pointerType: "mouse" });

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent(club.club);
    expect(tooltip).toHaveTextContent(`GW${latest.event}`);
    expect(tooltip).toHaveTextContent(`${club.topElevenHits}/11`);
    expect(
      container.querySelector(
        `.xstart-cumulative-line[data-club="${club.club}"]`,
      ),
    ).toHaveClass("is-active");

    fireEvent.pointerMove(hitArea!, { clientX: 100, pointerType: "mouse" });
    const first = validation.events[0]!;
    const firstClub = first.clubs.find((entry) => entry.club === club.club)!;
    expect(tooltip).toHaveTextContent(`GW${first.event}`);
    expect(tooltip).toHaveTextContent(`${firstClub.topElevenHits}/11`);
  });
});
