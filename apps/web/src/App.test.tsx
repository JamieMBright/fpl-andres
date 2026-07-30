import teamStateCases from "../../../packages/contracts/fixtures/public-team-state-cases.json";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "./App";
import { saveCachedPublicTeamState } from "./state/team-analysis";
import {
  loadTeamStateOverrides,
  saveTeamStateOverrides,
} from "./state/team-state-overrides";

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

  it("opens analysis for a valid FPL team ID", async () => {
    const user = userEvent.setup();
    renderApplication();

    expect(
      screen.getByRole("heading", {
        name: "Let me look at your squad.",
      }),
    ).not.toHaveFocus();
    await user.type(screen.getByLabelText("Your FPL team ID"), "123456");
    await user.click(screen.getByRole("button", { name: "Analyse my squad" }));

    const analysisHeading = await screen.findByRole("heading", {
      name: "Analysis for team 123456",
    });
    expect(analysisHeading).toBeInTheDocument();
    expect(analysisHeading).toHaveFocus();
    expect(
      await screen.findByRole("status", { name: "Evidence status" }),
    ).toHaveTextContent("Observed snapshot ready");
    expect(screen.getByText("£1.7m")).toBeInTheDocument();
    expect(screen.getByText("£100.4m")).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Last-deadline squad" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(16);

    await user.click(screen.getByText(/Check my working/));
    expect(
      screen.getByText(firstSourceHash, { exact: false }),
    ).toBeInTheDocument();
  });

  it("offers keyboard bypass and describes only available analysis", () => {
    renderApplication();

    expect(
      screen.getByRole("link", { name: "Skip to content" }),
    ).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("link", { name: "Method" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Your team ID" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "I crunch" })).toBeVisible();
    // Step four has not been earned yet and must say so.
    expect(screen.getByText(/when the models have earned it/)).toBeVisible();
    expect(
      screen.queryByText(/captain and bench calls/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/chip roadmap/i)).not.toBeInTheDocument();
  });

  it("explains why a malformed team ID cannot be analysed", async () => {
    const user = userEvent.setup();
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
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json(
            { status: "degraded", reason: "fpl_unreachable" },
            { status: 503 },
          ),
        ),
    );

    renderApplication(`/team/${readyState.entryId}`);

    expect(
      await screen.findByText("Showing a stale verified snapshot"),
    ).toBeVisible();
    expect(
      screen.getByRole("status", { name: "Evidence status" }),
    ).toHaveTextContent("Showing a stale verified snapshot");
    expect(
      screen.getByRole("table", { name: "Last-deadline squad" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/FPL is temporarily unreachable/i)).toBeVisible();
  });

  it("keeps a validated snapshot visible while refresh is in flight", async () => {
    saveCachedPublicTeamState(localStorage, readyState.entryId, readyState);
    let resolveFetch!: (response: Response) => void;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockReturnValue(pendingResponse),
    );

    renderApplication(`/team/${readyState.entryId}`);

    expect(
      await screen.findByText("Refreshing a verified snapshot"),
    ).toBeVisible();
    expect(
      screen.getByRole("table", { name: "Last-deadline squad" }),
    ).toBeVisible();

    resolveFetch(Response.json({ status: "ready", state: readyState }));
    expect(await screen.findByText("Observed snapshot ready")).toBeVisible();
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

    renderApplication("/team/123");

    expect(
      await screen.findByRole("heading", { name: "No processed gameweek yet" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        /Try again after FPL publishes the first processed event/i,
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("table", { name: "Last-deadline squad" }),
    ).not.toBeInTheDocument();
  });

  it("recovers from a network error when the user retries", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(
        Response.json({ status: "ready", state: readyState }),
      );
    vi.stubGlobal("fetch", fetchApi);

    renderApplication(`/team/${readyState.entryId}`);

    expect(
      await screen.findByRole("heading", { name: "Network Request Failed" }),
    ).toBeVisible();
    expect(screen.getByText(/Check your connection/i)).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: "Retry analysis" }),
    );

    expect(
      screen.getByRole("region", { name: "Analysis result" }),
    ).toHaveFocus();
    expect(await screen.findByText("Observed snapshot ready")).toBeVisible();
    expect(fetchApi).toHaveBeenCalledTimes(2);
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
    const user = userEvent.setup();
    renderApplication(`/team/${readyState.entryId}`);
    await screen.findByText("Observed snapshot ready");

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
    const user = userEvent.setup();
    renderApplication(`/team/${readyState.entryId}`);
    await screen.findByText("Observed snapshot ready");

    await user.click(screen.getByText("Correct Current State"));
    await user.click(screen.getByRole("button", { name: "Save corrections" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(
      "at least one manager override is required",
    );
    expect(error).toHaveFocus();
  });

  it("marks and focuses the first invalid correction field", async () => {
    const user = userEvent.setup();
    renderApplication(`/team/${readyState.entryId}`);
    await screen.findByText("Observed snapshot ready");

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
    const user = userEvent.setup();
    renderApplication(`/team/${readyState.entryId}`);
    await screen.findByText("Observed snapshot ready");

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
    const user = userEvent.setup();
    renderApplication(`/team/${teamA}`);
    await screen.findByRole("heading", { name: `Analysis for team ${teamA}` });

    await user.click(
      screen.getByRole("link", { name: "Analyse another team" }),
    );
    await user.type(screen.getByLabelText("Your FPL team ID"), String(teamB));
    await user.click(screen.getByRole("button", { name: "Analyse my squad" }));

    const analysisHeading = await screen.findByRole("heading", {
      name: `Analysis for team ${teamB}`,
    });
    expect(analysisHeading).toHaveAttribute("translate", "no");
    expect(
      screen.queryByRole("heading", { name: `Analysis for team ${teamA}` }),
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
    const user = userEvent.setup();
    renderApplication(`/team/${readyState.entryId}`);
    await screen.findByText("Observed snapshot ready");

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
