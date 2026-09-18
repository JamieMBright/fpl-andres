import { publicTeamStateSchema } from "@fpl-andres/contracts";
import teamStateCases from "../../../../packages/contracts/fixtures/public-team-state-cases.json";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TeamAnalysisState } from "../state/team-analysis";

import { AnalysisResult } from "./AnalysisResult";

/**
 * Before a ball is kicked there is no processed gameweek, and no amount of
 * asking again will produce one. Offering "Retry analysis" there promises a
 * different answer that cannot arrive.
 */

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("AnalysisResult", () => {
  it.each<TeamAnalysisState>([
    { status: "degraded", reason: "fpl_unreachable" },
    { status: "degraded", reason: "fpl_refused" },
    { status: "degraded", reason: "fpl_rate_limited" },
    { status: "degraded", reason: "fpl_source_failed" },
    { status: "degraded", reason: "rate_limited" },
    { status: "unavailable", reason: "picks_unavailable", event: 4 },
  ])(
    "offers an in-season builder and retry for $reason without an opening plan",
    async (analysis) => {
      vi.useFakeTimers({ toFake: ["Date"] });
      vi.setSystemTime(new Date("2026-09-15T12:00:00Z"));
      render(
        <MemoryRouter>
          <AnalysisResult
            analysis={analysis}
            entryId={42}
            onRetry={() => undefined}
          />
        </MemoryRouter>,
      );
      expect(
        await screen.findByRole("heading", {
          name: "Build your gameweek 5 fifteen",
        }),
      ).toBeVisible();
      expect(
        screen.getByRole("button", { name: "Retry analysis" }),
      ).toBeVisible();
      expect(screen.queryByText(/Model opening plan/i)).toBeNull();
      expect(screen.queryByText(/What the plan will contain/i)).toBeNull();
    },
  );

  it.each<TeamAnalysisState>([
    { status: "unavailable", reason: "entry_unavailable" },
    { status: "degraded", reason: "source_contract_failed" },
    { status: "error", reason: "invalid_response" },
  ])("does not turn $reason into a manager squad", (analysis) => {
    render(
      <MemoryRouter>
        <AnalysisResult
          analysis={analysis}
          entryId={42}
          onRetry={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("heading", { name: /build.*fifteen/i }),
    ).toBeNull();
  });

  it("does not offer a network fallback for an invalid team ID", () => {
    render(
      <MemoryRouter>
        <AnalysisResult
          analysis={{ status: "error", reason: "network_error" }}
          entryId={-1}
          onRetry={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("heading", { name: /build.*fifteen/i }),
    ).toBeNull();
  });

  it("offers a local squad builder without retry before any event is processed", async () => {
    render(
      <MemoryRouter>
        <AnalysisResult
          analysis={{ status: "unavailable", reason: "no_processed_event" }}
          entryId={212_279}
          onRetry={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("button", { name: "Retry analysis" })).toBeNull();
    expect(
      await screen.findByRole("heading", { name: /build.*fifteen/i }),
    ).toBeVisible();
  });

  it("keeps the preseason builder visible when storage cannot be read", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-08-01T12:00:00Z"));
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("Storage blocked");
    });
    expect(() =>
      render(
        <MemoryRouter>
          <AnalysisResult
            analysis={{ status: "unavailable", reason: "no_processed_event" }}
            entryId={42}
            onRetry={() => undefined}
          />
        </MemoryRouter>,
      ),
    ).not.toThrow();
    expect(
      await screen.findByRole("heading", { name: /build.*fifteen/i }),
    ).toBeVisible();
  });

  it("offers retry and a local squad builder when the network failed", async () => {
    render(
      <MemoryRouter>
        <AnalysisResult
          analysis={{ status: "error", reason: "network_error" }}
          entryId={212_279}
          onRetry={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("button", { name: "Retry analysis" }),
    ).toBeVisible();
    expect(
      await screen.findByRole("heading", { name: /build.*fifteen/i }),
    ).toBeVisible();
  });

  it("does not show the preseason transfer panel beside a ready snapshot", () => {
    render(
      <MemoryRouter>
        <AnalysisResult
          analysis={{
            status: "ready",
            state: publicTeamStateSchema.parse(teamStateCases.valid[0]),
          }}
          entryId={123}
          onRetry={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(
      screen.queryByText(/FPL has not processed a gameweek for this entry/i),
    ).toBeNull();
  });
});
