import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { XStartCalibration } from "./XStartCalibration";
import validation from "../data/xstart-validation.json";
import { readXStartValidation } from "../state/xstart-validation";

const latest = validation.events.at(-1)!;

describe("XStartCalibration", () => {
  it("draws running season-average kit-coloured lines on a fixed 0-11 scale", () => {
    const { container } = render(<XStartCalibration />);
    const club = latest.clubs[0]!.club;

    expect(
      screen.getByRole("heading", { name: "How close was the predicted XI?" }),
    ).toBeVisible();
    expect(container.querySelectorAll(".xstart-cumulative-line")).toHaveLength(
      20,
    );
    expect(
      screen.getByRole("combobox", { name: "Performance period" }),
    ).toHaveValue("average");
    expect(
      screen.getByRole("img", {
        name: /season-to-date average xStart hits/i,
      }),
    ).toHaveTextContent("11");
    expect(screen.queryByText(/cumulative/i)).not.toBeInTheDocument();

    const points = container
      .querySelector(`.xstart-cumulative-line[data-club="${club}"]`)
      ?.getAttribute("points")
      ?.split(" ")
      .map((point) => Number(point.split(",")[1]));
    expect(points).toHaveLength(validation.events.length);
    const scores = validation.events.map(
      (event) =>
        event.clubs.find((entry) => entry.club === club)!.topElevenHits,
    );
    const runningAverage =
      scores.slice(0, 2).reduce((total, score) => total + score, 0) / 2;
    const seasonAverage =
      scores.reduce((total, score) => total + score, 0) / scores.length;
    expect(points?.[1]).toBeCloseTo(224 - (runningAverage / 11) * 184, 5);
    expect(points?.at(-1)).toBeCloseTo(224 - (seasonAverage / 11) * 184, 5);
    expect(screen.queryByText("0.9-1.0")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("uses single-select kit buttons to isolate and restore a club", () => {
    const { container } = render(<XStartCalibration />);
    const first = latest.clubs[0]!;
    const firstKit = screen.getByRole("button", { name: first.club });

    expect(firstKit).toHaveAttribute("aria-pressed", "false");
    expect(firstKit.querySelector(".ceefax-shirt")).not.toBeNull();
    fireEvent.click(firstKit);

    expect(firstKit).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelectorAll(".xstart-cumulative-line")).toHaveLength(
      1,
    );
    expect(
      screen.getByRole("button", {
        name: new RegExp(`^About ${first.club} .*xStart detail$`),
      }),
    ).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("listitem")
        .filter((row) => row.matches(".xstart-performance-bars li")),
    ).toHaveLength(1);

    fireEvent.click(firstKit);
    expect(firstKit).toHaveAttribute("aria-pressed", "false");
    expect(container.querySelectorAll(".xstart-cumulative-line")).toHaveLength(
      20,
    );
    expect(
      container.querySelectorAll(".xstart-performance-bars li"),
    ).toHaveLength(20);
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
      "Last 5GW average",
      ...validation.events.map((event) => `GW${event.event}`),
    ]);
    const lastFiveOption = screen.getByRole("option", {
      name: "Last 5GW average",
    });
    expect(lastFiveOption).toHaveProperty(
      "disabled",
      validation.events.length < 5,
    );
    expect(period).toHaveValue("average");
    expect(
      screen.getAllByRole("list", { name: "xStart performance by club" }),
    ).toHaveLength(1);
    const seasonScores = validation.events.flatMap((event) => {
      const row = event.clubs.find((entry) => entry.club === club.club);
      return row ? [row.topElevenHits] : [];
    });
    const seasonAverage =
      seasonScores.reduce((total, score) => total + score, 0) /
      seasonScores.length;
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

  it("does not draw an unplayed club at a partial gameweek", () => {
    const partial = {
      ...validation,
      events: validation.events.map((event) =>
        event.event === latest.event
          ? {
              ...event,
              clubs: event.clubs.filter((club) => club.club !== "ARS"),
            }
          : event,
      ),
    };
    const { container } = render(<XStartCalibration validation={partial} />);
    const period = screen.getByRole("combobox", { name: "Performance period" });

    fireEvent.change(period, { target: { value: String(latest.event) } });

    expect(
      container.querySelector(".xstart-performance-bars [data-score]"),
    ).not.toBeNull();
    expect(
      screen.queryByText("ARS", { selector: ".xstart-score-bar-label" }),
    ).not.toBeInTheDocument();
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

  it("automatically enables and calculates the latest five settled gameweeks", () => {
    const parsed = readXStartValidation(validation);
    const base = parsed.events[0]!;
    const club = base.clubs[0]!.club;
    const events = Array.from({ length: 6 }, (_, index) => ({
      ...base,
      event: index + 1,
      clubs: base.clubs.map((row) =>
        row.club === club ? { ...row, topElevenHits: index + 1 } : row,
      ),
    }));

    render(<XStartCalibration validation={{ ...parsed, events }} />);
    const lastFiveOption = screen.getByRole("option", {
      name: "Last 5GW average",
    });
    expect(lastFiveOption).toBeEnabled();
    fireEvent.change(
      screen.getByRole("combobox", { name: "Performance period" }),
      { target: { value: "last5" } },
    );

    expect(
      screen.getByRole("heading", { name: "Last 5GW average hits" }),
    ).toBeVisible();
    const clubRow = screen
      .getByText(club, { selector: ".xstart-score-bar-label" })
      .closest("li");
    expect(clubRow).not.toBeNull();
    expect(within(clubRow!).getByText("4.0/11")).toBeVisible();
    fireEvent.focus(
      screen.getByRole("button", {
        name: `About ${club} last 5GW average xStart detail`,
      }),
    );
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("GW2 2/11");
    expect(tooltip).toHaveTextContent("GW6 6/11");
    expect(tooltip).not.toHaveTextContent("GW1 1/11");
  });

  it("shows a point-anchored running average and raw score on pointer or keyboard focus", () => {
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
    expect(tooltip).toHaveTextContent(
      `Season-to-date average ${(
        validation.events.reduce(
          (total, event) =>
            total +
            event.clubs.find((entry) => entry.club === club.club)!
              .topElevenHits,
          0,
        ) / validation.events.length
      ).toFixed(1)}/11`,
    );
    expect(tooltip).toHaveTextContent(
      `GW${latest.event} score ${club.topElevenHits}/11`,
    );
    expect(tooltip).toHaveStyle({ left: "606px" });
    expect(tooltip.closest(".xstart-cumulative-chart")).not.toBeNull();
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

    fireEvent.pointerLeave(hitArea!);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.focus(hitArea!);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      `GW${latest.event} score ${club.topElevenHits}/11`,
    );
    expect(hitArea).toHaveAttribute("aria-describedby");
    fireEvent.keyDown(hitArea!, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
