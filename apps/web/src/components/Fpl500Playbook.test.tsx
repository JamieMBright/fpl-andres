import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Fpl500Playbook } from "./Fpl500Playbook";
import artifact from "../data/fpl500.json";
import { fineShare, integer } from "../format";

/**
 * The page exists to say two things a reader cannot get from the ranking
 * itself: how little of the register has been read, and that the fund does not
 * hold anything yet. Both are easy to lose to a redesign and neither is
 * visible in a screenshot, so both are pinned here.
 */
describe("Fpl500Playbook", () => {
  function draw() {
    return render(
      <MemoryRouter>
        <Fpl500Playbook />
      </MemoryRouter>,
    );
  }

  it("says how far the register has been read", () => {
    draw();

    // Four fifths of the ids have never been looked at. A page listing five
    // hundred managers without that is claiming a completeness it lacks.
    const swept = integer.format(artifact.sweptTo);
    expect(
      screen.getByText(new RegExp(`Swept to id ${swept}`)),
    ).toBeInTheDocument();
  });

  it("lists exactly the managers the artifact says it lists", () => {
    draw();
    const table = screen.getByRole("table");

    expect(within(table).getAllByRole("row")).toHaveLength(artifact.listed + 1);
  });

  it("links each entry to its own public history", () => {
    draw();
    const first = artifact.managers[0]!;

    expect(
      screen.getByRole("link", { name: String(first.entryId) }),
    ).toHaveAttribute(
      "href",
      `https://fantasy.premierleague.com/entry/${first.entryId}/history`,
    );
  });

  it("says the ordering inside the five hundred carries little", () => {
    // The scores span about 0.017 across all five hundred. Reading rank 12 as
    // better than rank 300 is the mistake this section exists to prevent.
    draw();

    expect(
      screen.getByRole("heading", { name: /order inside the five hundred/i }),
    ).toBeInTheDocument();
  });

  it("says plainly that the fund holds nothing yet", () => {
    draw();

    expect(artifact.portfolioEvents).toEqual([]);
    expect(screen.getByText(/Nothing captured yet/)).toBeInTheDocument();
  });

  it("quotes the reconciler's own coverage floor rather than a number typed here", () => {
    draw();

    expect(
      screen.getByText(new RegExp(fineShare.format(artifact.minimumCoverage))),
    ).toBeInTheDocument();
  });
});
