import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

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
    // The page may show this season's public Overall standings (entry ids are
    // public). It must not expose membership of the FPL500 cohort itself.
    expect(JSON.stringify(artifact.cataloguePortfolio)).not.toContain(
      "entryId",
    );
    expect(JSON.stringify(artifact.exactFpl500Portfolio)).not.toContain(
      "entryId",
    );
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

  it("reports how many gameweeks have been captured", () => {
    draw();

    expect(artifact.cataloguePortfolio.events.length).toBeGreaterThanOrEqual(0);
    expect(artifact.exactFpl500Portfolio.events.length).toBeGreaterThanOrEqual(
      0,
    );
    expect(screen.getByText("Catalogue at deadline")).toBeInTheDocument();
    expect(screen.getByText("Exact FPL500")).toBeInTheDocument();
    expect(screen.getByText(/2,786 managers/)).toBeInTheDocument();
    expect(
      screen.getByText(/post-deadline capture-era FPL500 membership/),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/picks read/)).toHaveLength(2);
  });

  it("shows what the armband returned once a week is fully scored", () => {
    draw();

    // The sidecar behind this is written only when every fixture in the round
    // has a confirmed score, so an unscored week must show no points at all
    // rather than a zero that reads as a blank.
    for (const series of [
      artifact.cataloguePortfolio,
      artifact.exactFpl500Portfolio,
    ]) {
      for (const [eventKey, entries] of Object.entries(
        series.captains as Record<
          string,
          { elementId: number; share: number; points?: number }[]
        >,
      )) {
        for (const entry of entries) {
          if (entry.points === undefined) continue;
          expect(
            screen.getAllByText(
              new RegExp(`${integer.format(entry.points)} pts`),
            ).length,
            `GW${eventKey} element ${entry.elementId}`,
          ).toBeGreaterThan(0);
        }
      }
    }
    const scored = [
      ...Object.values(
        artifact.cataloguePortfolio.captains as Record<
          string,
          { points?: number }[]
        >,
      ),
      ...Object.values(
        artifact.exactFpl500Portfolio.captains as Record<
          string,
          { points?: number }[]
        >,
      ),
    ]
      .flat()
      .filter((entry) => entry.points !== undefined);
    if (scored.length === 0) {
      expect(screen.queryByText(/ pts/)).toBeNull();
    }
  });

  it("draws the frames the analysis will use, with their axes", () => {
    draw();

    expect(screen.getAllByText(/awaiting gameweek 2/)).toHaveLength(2);
    expect(screen.getByText("In and out")).toBeInTheDocument();
    expect(screen.getByText("Hits taken")).toBeInTheDocument();
    expect(screen.getByText("GW1, across 500 squads")).toBeInTheDocument();
    expect(screen.getByText("Mean score")).toBeInTheDocument();
    expect(screen.getByText("Mean bench")).toBeInTheDocument();
    for (const position of [
      "Goalkeepers",
      "Defenders",
      "Midfielders",
      "Forwards",
    ]) {
      expect(screen.getByText(position)).toBeInTheDocument();
    }
  });

  it("puts the cohort headlines before the player catalogue", () => {
    draw();

    const mean = screen.getByText("Mean score");
    const holdings = screen.getByText("Who they own, by position");
    expect(
      mean.compareDocumentPosition(holdings) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps sub-one-percent players behind a disclosure", () => {
    draw();

    expect(screen.getAllByText(/below 1% ownership/i).length).toBeGreaterThan(
      0,
    );
  });

  it("opens the existing player profile from a holding", async () => {
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = vi.fn(function showModal(
        this: HTMLDialogElement,
      ) {
        this.setAttribute("open", "");
      });
    }
    const user = userEvent.setup();
    draw();
    const first = artifact.exactFpl500Portfolio.holdings["01"].find(
      (holding) => holding.ownedShare >= 0.01,
    );
    expect(first).toBeDefined();

    const name = first?.name ?? `Element ${String(first?.elementId)}`;
    const button = screen.getAllByRole("button", { name })[0];
    expect(button).toBeDefined();
    await user.click(button!);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
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
