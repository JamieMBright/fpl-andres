import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import artifact from "../data/fpl500.json";
import { fineShare, oneDecimal } from "../format";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import { Fpl500Teaser } from "./Fpl500Teaser";

describe("Fpl500Teaser", () => {
  it("advertises the measured cohort headlines", () => {
    render(
      <MemoryRouter>
        <Fpl500Teaser />
      </MemoryRouter>,
    );
    const aggregate = artifact.exactFpl500Portfolio.samples["01"].aggregate;
    const sample = artifact.exactFpl500Portfolio.samples["01"];

    expect(
      screen.getByText(oneDecimal.format(aggregate.totalPoints.mean)),
    ).toBeVisible();
    expect(
      screen.getByText(oneDecimal.format(aggregate.totalPoints.median)),
    ).toBeVisible();
    expect(screen.getByText(String(sample.responded))).toBeVisible();
    expect(
      screen.getByText(
        fineShare.format(
          (sample.responded - (aggregate.chips.none ?? 0)) / sample.responded,
        ),
      ),
    ).toBeVisible();
    const topOwned = [...artifact.exactFpl500Portfolio.holdings["01"]].sort(
      (left, right) => right.ownedShare - left.ownedShare,
    )[0];
    const topCaptain = artifact.exactFpl500Portfolio.captains["01"][0];
    if (!topOwned || !topCaptain) throw new Error("FPL500 headlines are empty");
    expect(screen.getByText("Top owned").closest("span")).toHaveTextContent(
      PLAYERS_BY_ELEMENT_ID.get(topOwned.elementId)?.name ?? "missing",
    );
    expect(screen.getByText("Top captain").closest("span")).toHaveTextContent(
      PLAYERS_BY_ELEMENT_ID.get(topCaptain.elementId)?.name ?? "missing",
    );
    expect(screen.getByRole("link", { name: /FPL500/i })).toHaveAttribute(
      "href",
      "/fpl500",
    );
  });
});
