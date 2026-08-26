import { publicTeamStateSchema } from "@fpl-andres/contracts";
import teamStateCases from "../../../../packages/contracts/fixtures/public-team-state-cases.json";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnalysisResult } from "./AnalysisResult";

/**
 * Before a ball is kicked there is no processed gameweek, and no amount of
 * asking again will produce one. Offering "Retry analysis" there promises a
 * different answer that cannot arrive.
 */

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("AnalysisResult", () => {
  it("offers a local squad builder without retry before any event is processed", () => {
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
      screen.getByRole("heading", { name: /build.*fifteen/i }),
    ).toBeVisible();
  });

  it("offers retry without a local squad builder when the network failed", () => {
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
      screen.queryByRole("heading", { name: /build.*fifteen/i }),
    ).toBeNull();
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
      screen.queryByText(/No gameweek of the 2026\/27 season has been played/i),
    ).toBeNull();
  });
});
