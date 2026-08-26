import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerPoolTable } from "./PlayerPoolTable";
import { forgetLastGoodPool } from "../state/player-pool";

/**
 * The point of the fallback is that the reader keeps a usable page. That is
 * only true if the page also tells them what they are looking at -- a stale
 * price presented as current is worse than no price, because a manager acts on
 * it. Both halves are asserted here.
 */

const BOOTSTRAP = {
  events: [{ id: 1, deadline_time: "2026-08-21T17:30:00Z" }],
  element_types: [
    { id: 1, singular_name_short: "GKP" },
    { id: 3, singular_name_short: "MID" },
  ],
  teams: [{ id: 1, code: 3, short_name: "ARS", name: "Arsenal" }],
  elements: [
    {
      id: 1,
      code: 141746,
      web_name: "B.Fernandes",
      element_type: 3,
      team: 1,
      now_cost: 90,
      status: "a",
    },
  ],
};

function respond(input: RequestInfo | URL, init?: ResponseInit): Response {
  return String(input).includes("fixtures")
    ? Response.json([], init)
    : Response.json(BOOTSTRAP, init);
}

describe("the player list when FPL is unavailable", () => {
  beforeEach(() => {
    forgetLastGoodPool();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("says the list is not current when the proxy served a retained copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation((input) =>
        Promise.resolve(
          respond(input, {
            headers: {
              "X-FPL-Stale": "1",
              "X-FPL-Stale-Age": "600",
              "X-FPL-Captured-At": new Date(Date.now() - 600_000).toISOString(),
            },
          }),
        ),
      ),
    );

    render(<PlayerPoolTable />);

    expect(await screen.findByText(/FPL is not answering/)).toBeInTheDocument();
    expect(await screen.findByText("B.Fernandes")).toBeInTheDocument();
  });

  it("offers a retry rather than telling the reader to reload", async () => {
    // A flag rather than a call count: the component asks for two documents at
    // once and each is retried, so counting calls would make the test depend on
    // the retry schedule.
    let down = true;
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockImplementation((input) =>
          down
            ? Promise.reject(new TypeError("network"))
            : Promise.resolve(respond(input)),
        ),
    );

    render(<PlayerPoolTable />);

    const retry = await screen.findByRole(
      "button",
      { name: "Try again" },
      {
        timeout: 10_000,
      },
    );
    down = false;
    await userEvent.click(retry);

    expect(await screen.findByText("B.Fernandes")).toBeInTheDocument();
  }, 20_000);
});
