import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Fpl500Playbook } from "./Fpl500Playbook";
import artifact from "../data/fpl500.json";
import { fineShare, integer } from "../format";

/**
 * Two claims here are easy to lose to a redesign and neither is visible in a
 * screenshot: that the page never names who is in FPL500, and that it says how
 * little of the register has been read.
 *
 * The first is the one that matters commercially. Who clears the bar is the
 * single thing in this repository somebody could copy outright, so the page
 * carries a distribution and the artifact behind it carries no entry ids at
 * all. A well-meaning change that adds "just the top ten" gives it away.
 */
describe("Fpl500Playbook", () => {
  function draw() {
    return render(
      <MemoryRouter>
        <Fpl500Playbook />
      </MemoryRouter>,
    );
  }

  it("names nobody in the ranking", () => {
    draw();

    expect(artifact.listed).toBe(0);
    expect(JSON.stringify(artifact.rankHistogram)).not.toContain("entryId");
    // The only entry ids the page may show are this season's public standings.
    expect(
      screen.queryByRole("link", { name: /^\d+$/ }),
    ).not.toBeInTheDocument();
  });

  it("publishes the distribution instead", () => {
    draw();

    expect(Object.keys(artifact.rankHistogram).length).toBeGreaterThan(1);
    for (const counts of Object.values(artifact.rankHistogram)) {
      expect(counts).toHaveLength(artifact.rankBins.length + 1);
    }
    expect(screen.getByText(/Where they finish/)).toBeInTheDocument();
  });

  it("makes the selected cohort's previous-season record obvious", () => {
    draw();

    const summary = screen.getByRole("region", {
      name: "Previous-season record",
    });
    expect(within(summary).getByText("Previous-season record")).toBeVisible();
    expect(within(summary).getByText("Top 1k finishes")).toBeVisible();
    expect(within(summary).getByText("Top 10k finishes")).toBeVisible();
    expect(within(summary).getByText("Top 100k finishes")).toBeVisible();
    expect(within(summary).getByText(/Observed/)).toBeVisible();
    expect(
      within(summary).getByText(/FPL histories through/),
    ).toBeInTheDocument();
  });

  it("says how far the register has been read", () => {
    draw();

    // Four fifths of the ids have never been looked at. A page about five
    // hundred managers without that is claiming a completeness it lacks.
    expect(
      screen.getByText(integer.format(artifact.sweptTo)),
    ).toBeInTheDocument();
    expect(screen.getByText(/still unread/)).toBeInTheDocument();
  });

  it("segments the page rather than running it together", () => {
    draw();

    for (const title of [
      "What it is",
      "How it is decided",
      "Who is scoring this season",
      "When it updates",
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });

  it("says plainly that nothing has been captured yet", () => {
    draw();

    expect(artifact.portfolioEvents).toEqual([]);
    expect(
      screen.getByText(/no FPL500 gameweek picks or captain choices/i),
    ).toBeInTheDocument();
  });

  it("draws the frames the analysis will use, with their axes", () => {
    draw();

    // An empty section says nothing about whether to come back. A frame with
    // the right axes says exactly what will be in it.
    expect(screen.getAllByText(/awaiting gameweek 1/).length).toBeGreaterThan(
      4,
    );
    expect(screen.getAllByText(/Gameweek/).length).toBeGreaterThan(3);
  });

  it("quotes the reconciler's own coverage floor rather than a number typed here", async () => {
    draw();

    // Inside a closed fold, so it is hidden from the accessibility tree.
    // jsdom does not open a `details` on a summary click, so it is asked for
    // directly rather than through an interaction that would not happen.
    await userEvent.click(
      screen.getByRole("button", {
        hidden: true,
        name: "About the coverage floor",
      }),
    );
    expect(
      within(screen.getByRole("tooltip")).getByText(
        new RegExp(fineShare.format(artifact.minimumCoverage)),
      ),
    ).toBeInTheDocument();
  });
});
