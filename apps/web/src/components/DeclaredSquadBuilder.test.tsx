import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeclaredSquadBuilder } from "./DeclaredSquadBuilder";
import { readDeclaredSquad } from "../state/declared-squad";
import {
  PLAYERS_BY_ELEMENT_ID,
  type SolverPlayer,
} from "../state/season-solver";

/**
 * Before the first deadline there is nothing public to read, so this is the
 * only route from a Team ID to a season plan. It must never accept a squad
 * that could not be entered into FPL, and never store one it rejected.
 */

const POOL = [...PLAYERS_BY_ELEMENT_ID.values()];

function legalSquad(): SolverPlayer[] {
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
  return picked;
}

async function fillSquad(squad: readonly SolverPlayer[]): Promise<void> {
  // `delay: null` removes userEvent's inter-event wait. Fifteen picks made it
  // most of this file's seventeen seconds, and nothing here asserts timing.
  const user = userEvent.setup({ delay: null });
  // The market lists by name, so each player is found by his own add button
  // rather than by a slot index the pitch no longer exposes.
  const search = screen.getByRole("searchbox", { name: /search/i });
  for (const player of squad) {
    // Pasted rather than typed: fifteen names one keystroke at a time takes
    // longer than the whole suite's per-test budget.
    await user.clear(search);
    await user.paste(player.name);
    await user.click(
      screen.getByRole("button", { name: `Add ${player.name}` }),
    );
  }
  await user.clear(search);
}

function renderBuilder() {
  render(
    <MemoryRouter>
      <DeclaredSquadBuilder entryId={42} />
    </MemoryRouter>,
  );
}

describe("DeclaredSquadBuilder", () => {
  // The builder asks for the live FPL list and replaces its market with it when
  // the answer arrives. Left to a real fetch that is a race: alone it fails
  // fast and the bundled pool stands, under a loaded suite it can land halfway
  // through the journey and rename every row the test is clicking on.
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline"))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  // Fifteen real interactions through a six-hundred-player market. The default
  // five seconds fits when the file runs alone and does not when the suite runs
  // in parallel, which is a property of the runner rather than of the code.
  const JOURNEY_TIMEOUT = 30_000;

  it(
    "locks in a legal fifteen and keeps it in this browser",
    async () => {
      renderBuilder();

      await fillSquad(legalSquad());
      await userEvent.click(
        screen.getByRole("button", { name: /lock this in/i }),
      );

      expect(
        readDeclaredSquad(window.localStorage, 42, 1)?.elementIds,
      ).toHaveLength(15);
      expect(
        screen.getByText(/now starts from these fifteen/i),
      ).toBeInTheDocument();
    },
    JOURNEY_TIMEOUT,
  );

  it(
    "refuses a squad that breaks a published rule and stores nothing",
    async () => {
      renderBuilder();

      // Four from one club. The market cannot prevent this the way it prevents a
      // duplicate, so it is the rule the validator has to catch.
      const counts = new Map<string, SolverPlayer[]>();
      for (const player of POOL) {
        counts.set(player.club, [...(counts.get(player.club) ?? []), player]);
      }
      const crowded = [...counts.values()].find((group) => group.length >= 4);
      if (!crowded) throw new Error("no club with four players in the pool");

      const squad = legalSquad();
      const swapped = squad.map((player, index) => {
        const replacement = crowded.find(
          (candidate) =>
            candidate.position === player.position &&
            !squad.some((held) => held.id === candidate.id),
        );
        return index < 4 && replacement ? replacement : player;
      });

      await fillSquad(swapped);

      expect(
        screen.getByRole("button", { name: /lock this in/i }),
      ).toBeDisabled();
      expect(readDeclaredSquad(window.localStorage, 42, 1)).toBeNull();
    },
    JOURNEY_TIMEOUT,
  );
});
