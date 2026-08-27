import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import artifact from "../data/fpl500.json";
import { fineShare, oneDecimal } from "../format";
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
    expect(
      screen.getByText(
        fineShare.format(aggregate.chips.bboost / sample.responded),
      ),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: /FPL500/i })).toHaveAttribute(
      "href",
      "/fpl500",
    );
  });
});
