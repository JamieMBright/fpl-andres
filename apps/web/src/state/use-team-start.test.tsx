import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { saveDeclaredSquad } from "./declared-squad";
import { PLAYERS_BY_ELEMENT_ID, type SolverPlayer } from "./season-solver";
import { useTeamStart, type TeamStartStatus } from "./use-team-start";

/**
 * Between seasons FPL publishes nothing, and until now that ended the plan.
 * A manager's own declared fifteen closes the gap, and these pin that it is
 * only ever his own claim: no squad stored, no plan.
 */

const POOL = [...PLAYERS_BY_ELEMENT_ID.values()];

function legalSquad(): number[] {
  const picked: SolverPlayer[] = [];
  const clubs = new Map<string, number>();
  const shape: [SolverPlayer["position"], number][] = [
    ["GKP", 2],
    ["DEF", 5],
    ["MID", 5],
    ["FWD", 3],
  ];
  for (const [position, required] of shape) {
    const candidates = POOL.filter(
      (player) => player.position === position,
    ).sort((left, right) => left.priceTenths - right.priceTenths);
    let taken = 0;
    for (const candidate of candidates) {
      if (taken === required) break;
      const held = clubs.get(candidate.club) ?? 0;
      if (held >= 3) continue;
      clubs.set(candidate.club, held + 1);
      picked.push(candidate);
      taken += 1;
    }
  }
  return picked.map((player) => player.id);
}

function Probe({ onStatus }: { onStatus: (status: TeamStartStatus) => void }) {
  onStatus(useTeamStart("42"));
  return null;
}

function preSeasonFetch(): typeof fetch {
  return vi.fn(async () =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          status: "unavailable",
          reason: "no_processed_event",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ),
  ) as unknown as typeof fetch;
}

describe("useTeamStart before the first deadline", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("plans from the fifteen the manager declared, as if played in gameweek 1", async () => {
    vi.stubGlobal("fetch", preSeasonFetch());
    saveDeclaredSquad(window.localStorage, 42, 1, legalSquad());
    const seen: { latest: TeamStartStatus } = {
      latest: { status: "idle" },
    };

    render(
      <Probe
        onStatus={(status) => {
          seen.latest = status;
        }}
      />,
    );

    await waitFor(() => {
      expect(seen.latest.status).toBe("ready");
    });
    const latest = seen.latest;
    if (latest.status !== "ready") return;
    expect(latest.source).toBe("declared");
    expect(latest.event).toBe(1);
    expect(latest.start.squad).toHaveLength(15);
    expect(latest.start.bankTenths).toBeGreaterThanOrEqual(0);
  });

  it("still refuses to invent a squad when nothing was declared", async () => {
    vi.stubGlobal("fetch", preSeasonFetch());
    const seen: { latest: TeamStartStatus } = {
      latest: { status: "idle" },
    };

    render(
      <Probe
        onStatus={(status) => {
          seen.latest = status;
        }}
      />,
    );

    await waitFor(() => {
      expect(seen.latest.status).toBe("failed");
    });
    const latest = seen.latest;
    if (latest.status !== "failed") return;
    expect(latest.reason).toBe("no_processed_event");
    expect(screen.queryByRole("table")).toBeNull();
  });
});
