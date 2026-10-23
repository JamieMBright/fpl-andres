import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";

import { expectedXi } from "../state/expected-xi";
import {
  XSTART_VALIDATION,
  latestXStartEvent,
} from "../state/xstart-validation";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";
import ExpectedXiPage from "./ExpectedXiPage";

describe("Expected XI page", () => {
  it("opens on the next gameweek and explains a frozen XI miss", async () => {
    // The page heads on whichever gameweek the published season opens with, so
    // naming one here dates the test to the week it was written.
    const { event } = expectedXi();
    const validationEvent =
      [...XSTART_VALIDATION.events]
        .reverse()
        .find((event) => event.complete !== false)?.event ??
      latestXStartEvent(XSTART_VALIDATION).event;

    render(
      <MemoryRouter>
        <ExpectedXiPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: `xStart GW${String(event)}` }),
    ).toBeVisible();
    expect(
      screen.getByRole("navigation", { name: "Expected XI clubs" }),
    ).toBeVisible();
    expect(screen.getAllByRole("link")).toHaveLength(20);
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(20);
    expect(document.body).toHaveTextContent(`GW${validationEvent} check`);
    const missedTeam = expectedXi().teams.find((team) =>
      team.validation?.selected.some(
        (row) => !row.started && PLAYERS_BY_ELEMENT_ID.has(row.elementId),
      ),
    );
    expect(missedTeam?.validation).toBeDefined();
    const frozenMiss = missedTeam?.validation?.selected.find(
      (row) => !row.started && PLAYERS_BY_ELEMENT_ID.has(row.elementId),
    );
    expect(frozenMiss).toBeDefined();
    const frozenMissName = PLAYERS_BY_ELEMENT_ID.get(
      frozenMiss!.elementId,
    )?.name;
    expect(frozenMissName).toBeDefined();
    await userEvent.click(
      screen.getByRole("button", {
        name: `About ${missedTeam!.club} GW${validationEvent} xStart check`,
      }),
    );
    expect(screen.getByRole("tooltip")).toHaveTextContent(frozenMissName!);
    expect(screen.getByRole("tooltip")).toHaveTextContent(/starters left out/i);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Frozen XI misses");
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "mean squared probability error",
    );
    const players = expectedXi().teams.flatMap((team) => [
      ...team.starters,
      ...team.reserves,
    ]);
    expect(
      document.querySelectorAll(".expected-xi-evidence-market"),
    ).toHaveLength(
      players.filter((player) => player.evidence === "market").length,
    );
    expect(
      document.querySelectorAll(".expected-xi-evidence-model"),
    ).toHaveLength(
      players.filter((player) => player.evidence === "model").length,
    );
    expect(
      screen.getAllByRole("button", { name: /About .* evidence/ }),
    ).toHaveLength(players.length);
    expect(document.querySelector(".expected-xi-evidence-legend")).toBeNull();
    expect(document.body).toHaveTextContent("Likely XI");
    expect(document.body).toHaveTextContent("Next in");
    await userEvent.click(screen.getByLabelText("Performance"));
    expect(
      screen.getByRole("heading", { name: "How close was the predicted XI?" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("navigation", { name: "Expected XI clubs" }),
    ).toBeNull();
  });
});
