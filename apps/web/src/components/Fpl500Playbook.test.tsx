import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { Fpl500Playbook, latestCapture } from "./Fpl500Playbook";
import artifact from "../data/fpl500.json";
import { fineShare, integer } from "../format";

// The page shows the newest gameweek FPL has scored, so pinning one here would
// date the test to the week it was written.
const LATEST_EVENT =
  latestCapture(
    artifact.exactFpl500Portfolio as Parameters<typeof latestCapture>[0],
  )?.event ?? Math.max(...artifact.exactFpl500Portfolio.events);
const NEXT_EVENT = LATEST_EVENT + 1;

describe("latestCapture", () => {
  const series = (
    events: number[],
    points: Record<string, number>,
  ): Parameters<typeof latestCapture>[0] => ({
    basis: "ranked-500",
    label: "Exact FPL500",
    events,
    samples: {},
    captains: {},
    holdings: Object.fromEntries(
      events.map((event) => {
        const key = String(event).padStart(2, "0");
        return [
          key,
          [
            {
              elementId: 1,
              code: 1,
              name: "P",
              position: "MID",
              club: "ARS",
              teamId: 1,
              priceTenths: 50,
              ownedShare: 0.5,
              startedShare: 0.5,
              captainedShare: 0,
              effectiveOwnership: 0.5,
              lastWeekPoints: points[key] ?? 0,
            },
          ],
        ];
      }),
    ),
  });

  it("shows the newest gameweek once FPL has scored it", () => {
    expect(latestCapture(series([1, 2], { "01": 5, "02": 7 }))?.event).toBe(2);
  });

  it("holds back a round captured before its points are confirmed", () => {
    // A round is captured the moment its deadline passes, hours before FPL
    // confirms the points. Showing it then put a wall of zeros on the page.
    expect(latestCapture(series([1, 2], { "01": 5, "02": 0 }))?.event).toBe(1);
  });

  it("still shows the opening round while nothing has been scored", () => {
    expect(latestCapture(series([1], { "01": 0 }))?.event).toBe(1);
  });

  it("has nothing to show before the first capture", () => {
    expect(latestCapture(series([], {}))).toBeNull();
  });
});

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

    // Inside the collapsed "What it is" fold, same as the coverage floor
    // tooltip below: present in the DOM, not visible until opened.
    const heading = screen.getByRole("heading", { name: "What it is" });
    const fold = heading.closest("details");
    expect(fold).not.toBeNull();
    const summary = within(fold!);
    expect(summary.getByText("Top 1k finishes")).toBeInTheDocument();
    expect(summary.getByText("Top 10k finishes")).toBeInTheDocument();
    expect(summary.getByText("Top 100k finishes")).toBeInTheDocument();
    expect(summary.getByText(/Observed/)).toBeInTheDocument();
    expect(summary.getByText(/FPL histories through/)).toBeInTheDocument();
  });

  it("leads with a so-what hook and a jump nav, not the scanning numbers", () => {
    draw();

    expect(
      screen.getByText(/carefully selected group of managers/),
    ).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Jump to a section" });
    for (const label of [
      "Rank",
      "Captaincy",
      "Players",
      "Chips",
      "Value",
      "Transfers",
      "Squad",
    ]) {
      expect(within(nav).getByRole("link", { name: label })).toBeVisible();
    }
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
    expect(screen.queryByText("Catalogue at deadline")).not.toBeInTheDocument();
    expect(screen.getByText("Exact FPL500")).toBeInTheDocument();
    // Membership provenance and armband sample are both per gameweek captured,
    // so these counts grow with the season rather than staying at one.
    expect(
      screen.getAllByText(/post-deadline capture-era FPL500 membership/),
    ).toHaveLength(artifact.exactFpl500Portfolio.events.length);
    expect(screen.getAllByText(/picks read/)).toHaveLength(
      artifact.exactFpl500Portfolio.events.length,
    );
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

    expect(
      screen.getAllByText(
        new RegExp(`awaiting gameweek ${String(NEXT_EVENT)}`),
      ),
    ).toHaveLength(1);
    expect(screen.getByText("Hits taken")).toBeInTheDocument();
    expect(
      screen.getByText("Who they are buying and selling"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`GW${String(LATEST_EVENT)}, across 500 squads`),
    ).toBeInTheDocument();
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
