import { readFileSync } from "node:fs";
import { join } from "node:path";

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
const STYLES = readFileSync(join(__dirname, "..", "styles.css"), "utf8");

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
    // Selected and pasted over rather than cleared and retyped. Clearing sends
    // the search back to empty, and an empty search renders the two hundred
    // rows the market caps at -- fifteen times, for nothing.
    await user.tripleClick(search);
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
  // Measured at eight seconds alone and forty under a full parallel suite on a
  // loaded machine, so the number is a safety net rather than a budget: it must
  // never be the thing that decides whether this journey works.
  const JOURNEY_TIMEOUT = 120_000;

  it("reveals the filtered player market forty rows at a time", async () => {
    renderBuilder();

    expect(document.querySelectorAll(".squad-market-list > li")).toHaveLength(
      40,
    );
    const more = screen.getByRole("button", { name: /show more players/i });
    await userEvent.click(more);

    expect(document.querySelectorAll(".squad-market-list > li")).toHaveLength(
      80,
    );
  });

  it("names the bounded desktop market as a keyboard scroll region", () => {
    renderBuilder();

    expect(
      screen.getByRole("region", { name: "Scrollable player market" }),
    ).toHaveAttribute("tabindex", "0");
  });

  it("uses opaque theme-invariant ink for every label on the pitch", () => {
    const start = STYLES.indexOf(".squad-pitch {");
    const pitchRules = STYLES.slice(
      start,
      STYLES.indexOf("/* Bars drawn", start),
    );

    expect(STYLES).toContain("--pitch-ink: var(--fa-pitch-ink);");
    expect(pitchRules).toContain("color: var(--pitch-ink);");
    expect(pitchRules).not.toContain("opacity:");
  });

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
