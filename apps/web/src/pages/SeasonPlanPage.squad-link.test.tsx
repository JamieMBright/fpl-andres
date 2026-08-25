import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { routes } from "../App";
import { readDeclaredSquad } from "../state/declared-squad";
import {
  PLAYERS_BY_ELEMENT_ID,
  type SolverPlayer,
} from "../state/season-solver";
import { currentPlanningEvent } from "../state/use-team-start";
import { encodeSquad } from "../state/squad-code";

/**
 * A phone that cleared its storage still has the link.
 *
 * Mobile Safari bins script-written storage after a week without a first-party
 * visit, which took a manager's declared fifteen with it. A bookmark is not
 * script-written storage, so the squad rides in the query string too.
 */

const ENTRY_ID = 212_279;
const SETTLE = 30_000;

vi.setConfig({ testTimeout: SETTLE });

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
    const candidates = [...PLAYERS_BY_ELEMENT_ID.values()]
      .filter((player) => player.position === position)
      .sort((left, right) => left.priceTenths - right.priceTenths);
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

function renderPlan(entry: string) {
  const router = createMemoryRouter(routes, { initialEntries: [entry] });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi
      .fn<typeof fetch>()
      .mockImplementation(async () =>
        Response.json({ status: "unavailable", reason: "no_processed_event" }),
      ),
  );
});

describe("the declared squad in a link", () => {
  it("puts a squad from the address bar back into a browser that lost it", async () => {
    const squad = legalSquad();
    const code = encodeSquad(squad);
    expect(code).not.toBeNull();
    const event = currentPlanningEvent();

    renderPlan(`/plan?team=${String(ENTRY_ID)}&squad=${code!}`);

    await waitFor(
      () => {
        expect(
          readDeclaredSquad(localStorage, ENTRY_ID, event)?.elementIds,
        ).toEqual(squad);
      },
      { timeout: SETTLE },
    );
  });

  it("leaves a squad already in this browser alone", async () => {
    const held = legalSquad();
    const other = [...held.slice(1), held[0]!].reverse();
    localStorage.setItem(
      `fpl-andres:declared-squad:v1:${String(ENTRY_ID)}:1`,
      JSON.stringify({
        entryId: ENTRY_ID,
        event: 1,
        elementIds: held,
        declaredAt: "2026-08-01T00:00:00.000Z",
      }),
    );

    renderPlan(`/plan?team=${String(ENTRY_ID)}&squad=${encodeSquad(other)!}`);

    await screen.findByRole("heading", { level: 1 }, { timeout: SETTLE });
    expect(readDeclaredSquad(localStorage, ENTRY_ID, 1)?.elementIds).toEqual(
      held,
    );
  });

  it("writes the squad it is planning from into the address bar", async () => {
    const squad = legalSquad();
    localStorage.setItem(
      `fpl-andres:declared-squad:v1:${String(ENTRY_ID)}:1`,
      JSON.stringify({
        entryId: ENTRY_ID,
        event: 1,
        elementIds: squad,
        declaredAt: "2026-08-01T00:00:00.000Z",
      }),
    );

    const router = renderPlan(`/plan?team=${String(ENTRY_ID)}`);

    await waitFor(
      () => {
        const search = new URLSearchParams(router.state.location.search);
        expect(search.get("squad")).toBe(encodeSquad(squad));
      },
      { timeout: SETTLE },
    );
  });

  it("ignores a corrupted link rather than planning from half a squad", async () => {
    const code = encodeSquad(legalSquad())!;

    renderPlan(`/plan?team=${String(ENTRY_ID)}&squad=${code.slice(0, -6)}`);

    await screen.findByRole("heading", { level: 1 }, { timeout: SETTLE });
    expect(readDeclaredSquad(localStorage, ENTRY_ID, 1)).toBeNull();
  });
});
