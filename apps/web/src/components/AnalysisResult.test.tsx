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
  it("offers no retry when the season has not started", () => {
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
  });

  it("offers retry and a local squad builder when the network failed", () => {
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
      screen.getByRole("heading", { name: /build.*fifteen/i }),
    ).toBeVisible();
    expect(screen.getByText(/not your team/i)).toBeVisible();
  });
});
