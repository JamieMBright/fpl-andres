import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import artifact from "../data/fpl500.json";
import { integer } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { transferFlow } from "../state/transfer-flow";
import { latestCaptured, type Fpl500 } from "./Fpl500Playbook";
import { Fpl500Teaser } from "./Fpl500Teaser";

describe("Fpl500Teaser", () => {
  it("advertises the latest measured cohort headlines", () => {
    render(
      <MemoryRouter>
        <Fpl500Teaser />
      </MemoryRouter>,
    );
    const data = artifact as Fpl500;
    const series = data.exactFpl500Portfolio;
    const latest = latestCaptured(series);
    if (!latest) throw new Error("FPL500 teaser has no captured gameweeks");
    const sample = series.samples[latest.key];
    if (!sample?.aggregate)
      throw new Error("FPL500 teaser aggregate is missing");
    const aggregate = sample.aggregate;
    const standing = aggregate.seasonStanding?.flatMap((row) =>
      row.overallRank === null ? [] : [row.overallRank],
    );
    const bestRank = standing ? Math.min(...standing) : null;
    const meanRank = standing
      ? Math.round(
          standing.reduce((total, rank) => total + rank, 0) / standing.length,
        )
      : null;
    const eventsThroughLatest = series.events.filter(
      (event) => event <= latest.event,
    );
    const movement =
      eventsThroughLatest.length > 1
        ? transferFlow(
            {
              ...series,
              events: eventsThroughLatest,
            },
            1,
          )
        : [];

    expect(
      screen.getByRole("link", {
        name: new RegExp(`FPL500 · GW${latest.event}`, "i"),
      }),
    ).toBeVisible();
    expect(screen.getByText(String(sample.responded))).toBeVisible();
    expect(
      screen.getByText("Best overall rank").closest("span"),
    ).toHaveTextContent(integer.format(bestRank ?? 0));
    expect(
      screen.getByText("Mean overall rank").closest("span"),
    ).toHaveTextContent(integer.format(meanRank ?? 0));
    const topCaptain = series.captains[latest.key]?.[0];
    if (!topCaptain) throw new Error("FPL500 captain headline is empty");
    expect(
      screen.getByText("Most captained").closest("span"),
    ).toHaveTextContent(
      PLAYERS_BY_ELEMENT_ID.get(topCaptain.elementId)?.name ?? "missing",
    );
    if (movement.length > 0) {
      expect(
        screen.getByText("Most transferred in").closest("span"),
      ).toHaveTextContent(movement[0]!.name);
      expect(
        screen.getByText("Most transferred out").closest("span"),
      ).toHaveTextContent(movement.at(-1)!.name);
    } else {
      expect(screen.getByText("Most transferred in")).toBeVisible();
      expect(screen.getByText("Most transferred out")).toBeVisible();
      expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    }
    expect(screen.getByText("Exact sample").closest("span")).toHaveTextContent(
      String(sample.responded),
    );
    expect(screen.getByRole("link", { name: /FPL500/i })).toHaveAttribute(
      "href",
      "/fpl500",
    );
  });
});
