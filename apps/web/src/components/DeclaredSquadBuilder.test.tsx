import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

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
  const user = userEvent.setup();
  const selects = screen.getAllByRole("combobox");
  for (const [index, player] of squad.entries()) {
    const select = selects[index];
    if (!select) throw new Error("missing squad slot");
    await user.selectOptions(select, String(player.id));
  }
}

function renderBuilder() {
  render(
    <MemoryRouter>
      <DeclaredSquadBuilder entryId={42} />
    </MemoryRouter>,
  );
}

describe("DeclaredSquadBuilder", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("locks in a legal fifteen and keeps it in this browser", async () => {
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
  });

  it("refuses a squad that breaks a published rule and stores nothing", async () => {
    renderBuilder();

    const squad = legalSquad();
    const dearest = POOL.filter((player) => player.position === "FWD").sort(
      (left, right) => right.priceTenths - left.priceTenths,
    );
    const replacement = dearest[0];
    if (!replacement) throw new Error("no forward in the pool");
    const swapped = squad.map((player, index) =>
      index === 14 ? replacement : player,
    );
    // Same forward twice: a duplicate FPL would never accept.
    swapped[13] = replacement;

    await fillSquad(swapped);

    expect(
      screen.getByRole("button", { name: /lock this in/i }),
    ).toBeDisabled();
    expect(readDeclaredSquad(window.localStorage, 42, 1)).toBeNull();
  });
});
