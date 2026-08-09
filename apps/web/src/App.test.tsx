import teamStateCases from "../../../packages/contracts/fixtures/public-team-state-cases.json";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "./App";
import { saveCachedPublicTeamState } from "./state/team-analysis";
import {
  loadTeamStateOverrides,
  saveTeamStateOverrides,
} from "./state/team-state-overrides";

/**
 * Query budget for a settled snapshot. These assert behaviour, and the default
 * one second is a threshold on machine load rather than on the page. Every test
 * here now mounts the plan, which is the heaviest route in the app, so the
 * whole file gets the same allowance.
 */
const SETTLE = 30_000;

vi.setConfig({ testTimeout: SETTLE });

const readyState = {
  ...teamStateCases.valid[0]!,
  stateAsOf: "2026-07-20T10:30:00Z",
  dataAvailableAt: "2026-07-20T12:30:00Z",
  sourceHashes: [
    ...teamStateCases.valid[0]!.sourceHashes,
    `sha256:${"c".repeat(64)}`,
  ],
};
const firstSourceHash = readyState.sourceHashes[0]!;

function renderApplication(initialEntry = "/") {
  const router = createMemoryRouter(routes, {
    initialEntries: [initialEntry],
  });
  render(<RouterProvider router={router} />);
  return router;
}

describe("team analysis entry", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(async (input) => {
        const entryId = Number(String(input).split("/").at(-1));
        return Response.json({
          status: "ready",
          state: { ...readyState, entryId },
        });
      }),
    );
  });

  it(
    "opens analysis for a valid FPL team ID",
    async () => {
      const user = userEvent.setup({ delay: null });
      renderApplication();

      expect(
        screen.getByRole("heading", {
          name: "Welcome to FPL Andres.",
        }),
      ).not.toHaveFocus();
      await user.type(screen.getByLabelText("Your FPL team ID"), "123456");
      await user.click(
        screen.getByRole("button", { name: "Analyse my squad" }),
      );

      const analysisHeading = await screen.findByRole(
        "heading",
        { name: "Every gameweek to the end." },
        { timeout: SETTLE },
      );
      expect(analysisHeading).toBeInTheDocument();
      // The heading is in the document one commit before the effect that focuses
      // it has run. Asserting in the same tick passes alone and fails under a
      // loaded suite, which is a statement about the machine and not the page.
      await waitFor(() => {
        expect(analysisHeading).toHaveFocus();
      });
      // The status region mounts empty and fills once the snapshot resolves, so
      // this waits for the text rather than for the region.
      await screen.findByText("Observed snapshot ready", undefined, {
        timeout: SETTLE,
      });
      expect(screen.getByText("£1.7m")).toBeInTheDocument();
      expect(screen.getByText("£100.4m")).toBeInTheDocument();
      expect(
        await screen.findByRole(
          "list",
          { name: "Substitutes in order" },
          { timeout: SETTLE },
        ),
      ).toBeInTheDocument();

      await user.click(screen.getByText("Same squad as a table"));
      expect(
        screen.getByRole("table", { name: "Last-deadline squad" }),
      ).toBeInTheDocument();
      expect(screen.getAllByRole("row")).toHaveLength(16);

      await user.click(screen.getByText(/Check my working/));
      expect(
        screen.getByText(firstSourceHash, { exact: false }),
      ).toBeInTheDocument();
    },
    SETTLE,
  );

  it("offers keyboard bypass and describes only available analysis", () => {
    renderApplication();

    expect(
      screen.getByRole("link", { name: "Skip to content" }),
    ).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    // Every destination is reachable from the shell, and the five that carry
    // the work are on the index page as well as in the bar.
    for (const name of [
      "Plan",
      "Players",
      "Analysis",
      "Method",
      "Calibration",
    ]) {
      expect(screen.getAllByRole("link", { name }).length).toBeGreaterThan(2);
    }
    // FAQ and Kits are wayfinding, not the main event: bar and footer only.
    for (const name of ["FAQ", "Kits"]) {
      expect(screen.getAllByRole("link", { name }).length).toBeGreaterThan(0);
    }
    // Capability is stated by what the page offers, not by a page full of
    // promises about what it will offer one day.
    expect(
      screen.queryByText(/captain and bench calls/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/chip roadmap/i)).not.toBeInTheDocument();
  });

  it("explains why a malformed team ID cannot be analysed", async () => {
    const user = userEvent.setup({ delay: null });
    const router = renderApplication();

    await user.type(screen.getByLabelText("Your FPL team ID"), "abc");
    await user.click(screen.getByRole("button", { name: "Analyse my squad" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a numeric FPL team ID.",
    );
    expect(screen.getByLabelText("Your FPL team ID")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(router.state.location.pathname).toBe("/");
  });

  it("keeps a validated snapshot visible when refresh is degraded", async () => {
    saveCachedPublicTeamState(localStorage, readyState.entryId, readyState);
    // A fresh Response per call: a body can only be read once, and the page
    // makes two fetches. Sharing one instance made whichever consumer read
    // first the only one that saw anything.
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockImplementation(async () =>
          Response.json(
            { status: "degraded", reason: "fpl_unreachable" },
            { status: 503 },
          ),
        ),
    );

    renderApplication(`/plan?team=${String(readyState.entryId)}`);

    expect(
      await screen.findByText("Showing a stale verified snapshot", undefined, {
        timeout: SETTLE,
      }),
    ).toBeVisible();
    expect(
      screen.getByRole("status", { name: "Evidence status" }),
    ).toHaveTextContent("Showing a stale verified snapshot");
    expect(
      await screen.findByRole(
        "list",
        { name: "Substitutes in order" },
        { timeout: SETTLE },
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/FPL is temporarily unreachable/i)).toBeVisible();
  });

  it("keeps a validated snapshot visible while refresh is in flight", async () => {
    saveCachedPublicTeamState(localStorage, readyState.entryId, readyState);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    // A fresh Response per call. One shared instance has its body read twice
    // under StrictMode's double effect, and the second read throws.
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockImplementation(async () =>
          gate.then(() =>
            Response.json({ status: "ready", state: readyState }),
          ),
        ),
    );

    renderApplication(`/plan?team=${String(readyState.entryId)}`);

    expect(
      await screen.findByText("Refreshing a verified snapshot", undefined, {
        timeout: SETTLE,
      }),
    ).toBeVisible();
    expect(
      await screen.findByRole(
        "list",
        { name: "Substitutes in order" },
        { timeout: SETTLE },
      ),
    ).toBeVisible();

    release();
    expect(
      await screen.findByText("Observed snapshot ready", undefined, {
        timeout: SETTLE,
      }),
    ).toBeVisible();
  });

  it("explains a valid unavailable result without inventing state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        Response.json({
          status: "unavailable",
          reason: "no_processed_event",
        }),
      ),
    );

    renderApplication("/plan?team=123");

    expect(
      await screen.findByRole("heading", { name: /season hasn.t started/i }),
    ).toBeVisible();
    expect(
      screen.getByText(/FPL wipes every squad between seasons/i),
    ).toBeVisible();
    expect(
      screen.queryByRole("list", { name: "Substitutes in order" }),
    ).not.toBeInTheDocument();
    // The page must still be worth landing on: the manager's own record and
    // the plan that follows it are both real, and neither needs a live squad.
    expect(
      await screen.findByRole("heading", { name: /transfer plan/i }),
    ).toBeVisible();
  });

  it("rides out a single dropped connection without troubling the user", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValue(Response.json({ status: "ready", state: readyState }));
    vi.stubGlobal("fetch", fetchApi);

    renderApplication(`/plan?team=${String(readyState.entryId)}`);

    expect(
      await screen.findByText("Observed snapshot ready", undefined, {
        timeout: SETTLE,
      }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Network Request Failed" }),
    ).not.toBeInTheDocument();
  });

  it("recovers from a sustained network error when the user retries", async () => {
    const offline = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", offline);

    renderApplication(`/plan?team=${String(readyState.entryId)}`);

    // The fetch retries with backoff before declaring failure, which takes
    // longer than the default one-second query timeout.
    expect(
      await screen.findByRole(
        "heading",
        { name: "Network Request Failed" },
        { timeout: 10_000 },
      ),
    ).toBeVisible();
    expect(screen.getByText(/Check your connection/i)).toBeVisible();

    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json({ status: "ready", state: readyState }),
        ),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Retry analysis" }),
    );

    expect(
      screen.getByRole("region", { name: "Analysis result" }),
    ).toHaveFocus();
    expect(
      await screen.findByText("Observed snapshot ready", undefined, {
        timeout: SETTLE,
      }),
    ).toBeVisible();
  });

  /**
   * The button kept the previous failure on screen for the whole request, so a
   * retry that failed the same way changed nothing a reader could see. Clicking
   * has to say "working" before it can say anything else.
   */
  it("shows the retry working, even when it fails the same way again", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")),
    );

    renderApplication(`/plan?team=${String(readyState.entryId)}`);

    expect(
      await screen.findByRole(
        "heading",
        { name: "Network Request Failed" },
        { timeout: 10_000 },
      ),
    ).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: "Retry analysis" }),
    );

    expect(
      screen.getByRole("status", { name: "Evidence status" }),
    ).toHaveTextContent(/Loading public team state/i);
  });

  it("renders a recoverable page for unknown routes", () => {
    renderApplication("/not-a-real-page");

    expect(
      screen.getByRole("heading", { name: "Nothing here." }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Back to the Team ID" }),
    ).toHaveAttribute("href", "/");
  });

  it("stores manager corrections separately against the public deadline", async () => {
    const user = userEvent.setup({ delay: null });
    renderApplication(`/plan?team=${String(readyState.entryId)}`);
    await screen.findByText("Observed snapshot ready", undefined, {
      timeout: SETTLE,
    });

    await user.click(screen.getByText("Correct Current State"));
    await user.type(screen.getByLabelText("Current bank (£m)"), "1.2");
    await user.type(screen.getByLabelText("Available free transfers"), "2");
    await user.type(
      screen.getByLabelText("Available chips"),
      "wildcard, bench_boost",
    );
    await user.click(
      screen.getByRole("button", { name: "Add queued transfer" }),
    );
    await user.type(screen.getByLabelText("Player out"), "101");
    await user.type(screen.getByLabelText("Player in"), "201");
    await user.type(screen.getByLabelText("Selling price (£m)"), "6.0");
    await user.type(screen.getByLabelText("Purchase price (£m)"), "6.5");
    await user.click(screen.getByRole("button", { name: "Save corrections" }));

    expect(
      screen.getByRole("status", { name: "Manager correction status" }),
    ).toHaveTextContent("Manager corrections saved");
    expect(
      loadTeamStateOverrides(
        localStorage,
        readyState.entryId,
        readyState.stateAsOf,
      ),
    ).toMatchObject({
      source: "manager",
      basedOnStateAsOf: readyState.stateAsOf,
      bankTenths: 12,
      availableFreeTransfers: 2,
      currentSquad: null,
      queuedTransfers: [
        {
          elementOutId: 101,
          elementInId: 201,
          sellingPriceTenths: 60,
          purchasePriceTenths: 65,
        },
      ],
      availableChips: ["bench_boost", "wildcard"],
    });
  });

  it("focuses an actionable error when no correction is supplied", async () => {
    const user = userEvent.setup({ delay: null });
    renderApplication(`/plan?team=${String(readyState.entryId)}`);
    await screen.findByText("Observed snapshot ready", undefined, {
      timeout: SETTLE,
    });

    await user.click(screen.getByText("Correct Current State"));
    await user.click(screen.getByRole("button", { name: "Save corrections" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(
      "at least one manager override is required",
    );
    expect(error).toHaveFocus();
  });

  it("marks and focuses the first invalid correction field", async () => {
    const user = userEvent.setup({ delay: null });
    renderApplication(`/plan?team=${String(readyState.entryId)}`);
    await screen.findByText("Observed snapshot ready", undefined, {
      timeout: SETTLE,
    });

    await user.click(screen.getByText("Correct Current State"));
    const bank = screen.getByLabelText("Current bank (£m)");
    await user.type(bank, "1.23");
    await user.click(screen.getByRole("button", { name: "Save corrections" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Current bank must be a non-negative amount with at most 1 decimal place.",
    );
    expect(bank).toHaveAttribute("aria-invalid", "true");
    expect(bank).toHaveFocus();
  });

  it("removes saved manager corrections after confirmation", async () => {
    saveTeamStateOverrides(localStorage, readyState.entryId, {
      source: "manager",
      basedOnStateAsOf: readyState.stateAsOf,
      updatedAt: "2026-07-29T20:00:00Z",
      bankTenths: 12,
      availableFreeTransfers: null,
      currentSquad: null,
      queuedTransfers: null,
      availableChips: null,
    });
    const user = userEvent.setup({ delay: null });
    renderApplication(`/plan?team=${String(readyState.entryId)}`);
    await screen.findByText("Observed snapshot ready", undefined, {
      timeout: SETTLE,
    });

    await user.click(screen.getByText("Correct Current State"));
    await user.click(
      screen.getByRole("button", { name: "Remove saved corrections" }),
    );

    expect(
      screen.getByRole("alertdialog", { name: "Remove saved corrections?" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Keep corrections" }),
    ).toHaveFocus();
    expect(
      loadTeamStateOverrides(
        localStorage,
        readyState.entryId,
        readyState.stateAsOf,
      ),
    ).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Keep corrections" }));
    expect(
      screen.queryByRole("alertdialog", { name: "Remove saved corrections?" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove saved corrections" }),
    ).toHaveFocus();
    await user.click(
      screen.getByRole("button", { name: "Remove saved corrections" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Remove corrections now" }),
    );

    expect(
      screen.getByRole("status", { name: "Manager correction status" }),
    ).toHaveTextContent("Manager corrections removed");
    expect(
      loadTeamStateOverrides(
        localStorage,
        readyState.entryId,
        readyState.stateAsOf,
      ),
    ).toBeNull();
  });

  it("does not render team A's snapshot after navigating to team B", async () => {
    const teamA = readyState.entryId;
    const teamB = teamA === 123456 ? 654321 : 123456;
    saveCachedPublicTeamState(localStorage, teamA, {
      ...readyState,
      entryId: teamA,
    });
    // Team A is cached and team B is not, so B must not inherit A's squad
    // while its own request is in flight. The result region is keyed on the id
    // to force a fresh mount rather than reusing the previous team's.
    renderApplication(`/plan?team=${String(teamB)}`);

    await screen.findByRole("heading", { name: "Every gameweek to the end." });
    // A's cached snapshot must not be presented as B's. Its squad value is the
    // cheapest thing to look for that only A's snapshot would render.
    expect(
      screen.queryByRole("region", { name: "Squad value" }),
    ).not.toBeInTheDocument();
  });

  it("closes the remove-corrections dialog with Escape and restores focus", async () => {
    saveTeamStateOverrides(localStorage, readyState.entryId, {
      source: "manager",
      basedOnStateAsOf: readyState.stateAsOf,
      updatedAt: "2026-07-29T20:00:00Z",
      bankTenths: 12,
      availableFreeTransfers: null,
      currentSquad: null,
      queuedTransfers: null,
      availableChips: null,
    });
    const user = userEvent.setup({ delay: null });
    renderApplication(`/plan?team=${String(readyState.entryId)}`);
    await screen.findByText("Observed snapshot ready", undefined, {
      timeout: SETTLE,
    });

    await user.click(screen.getByText("Correct Current State"));
    await user.click(
      screen.getByRole("button", { name: "Remove saved corrections" }),
    );
    expect(
      screen.getByRole("alertdialog", { name: "Remove saved corrections?" }),
    ).toBeVisible();

    await user.keyboard("{Escape}");

    expect(
      screen.queryByRole("alertdialog", { name: "Remove saved corrections?" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove saved corrections" }),
    ).toHaveFocus();
  });
});
