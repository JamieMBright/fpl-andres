import teamStateCases from "../../../packages/contracts/fixtures/public-team-state-cases.json";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "./App";
import { saveCachedPublicTeamState } from "./state/team-analysis";

const readyState = teamStateCases.valid[0]!;
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
        name: "What should your next FPL move be?",
      }),
    ).not.toHaveFocus();
    await user.type(screen.getByLabelText("FPL team ID"), "123456");
    await user.click(screen.getByRole("button", { name: "Analyse team" }));

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

    await user.click(screen.getByText(/Inspect 2 source hashes/));
    expect(
      screen.getByText(firstSourceHash, { exact: false }),
    ).toBeInTheDocument();
  });

  it("explains why a malformed team ID cannot be analysed", async () => {
    const user = userEvent.setup();
    const router = renderApplication();

    await user.type(screen.getByLabelText("FPL team ID"), "abc");
    await user.click(screen.getByRole("button", { name: "Analyse team" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a numeric FPL team ID.",
    );
    expect(screen.getByLabelText("FPL team ID")).toHaveAttribute(
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

    expect(await screen.findByText("Observed snapshot ready")).toBeVisible();
    expect(fetchApi).toHaveBeenCalledTimes(2);
  });
});
