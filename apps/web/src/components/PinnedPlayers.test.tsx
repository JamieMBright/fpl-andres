import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PinnedPlayers } from "./PinnedPlayers";
import type { AnalysisPlayer } from "../state/analysis-pool";
import { DEFAULT_VIEW } from "../state/scatter-view";

/**
 * The comparison card names a player and, until now, stopped there. Everything
 * that decides whether to buy him -- the projection, the peer distribution,
 * the fixture run -- lives on the profile card, and there was no way to reach
 * it from the one screen where two players are being weighed against each
 * other.
 */

function player(overrides: Partial<AnalysisPlayer> = {}): AnalysisPlayer {
  return {
    elementId: 1,
    code: 1_000,
    name: "Test Player",
    position: "MID",
    club: "LEE",
    teamId: 9,
    teamCode: 2,
    available: true,
    priceTenths: 75,
    ownership: 12.5,
    minutes: 2_400,
    ninetiesPlayed: 26.7,
    totalPoints: 150,
    bonus: 12,
    expectedGoals: 6.1,
    expectedAssists: 4.2,
    expectedGoalInvolvements: 10.3,
    ictIndex: 180,
    influence: 600,
    creativity: 520,
    threat: 480,
    defensiveContribution: 40,
    defensiveContributionPer90: 1.5,
    defconBarRatio: 0.13,
    understat: null,
    ...overrides,
  };
}

describe("PinnedPlayers", () => {
  it("opens the profile from the player's name", async () => {
    const onOpen = vi.fn();
    const subject = player();

    render(
      <PinnedPlayers
        players={[subject]}
        pinned={[subject.code]}
        clubCodeByTeamId={new Map([[9, 2]])}
        fixtures={[]}
        onUnpin={() => undefined}
        onClear={() => undefined}
        onOpen={onOpen}
        view={DEFAULT_VIEW}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Test Player" }));

    expect(onOpen).toHaveBeenCalledWith(subject);
  });
});
