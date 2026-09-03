import type { PublicTeamPick } from "@fpl-andres/contracts";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveSquad } from "./LiveSquad";
import { fetchLiveGameweek } from "../state/live-gameweek";
import { projectionFor } from "../state/squad-projection";

// Bruno Fernandes, who is in the published artifact. The projection moves
// every time the artifact is refreshed, so the scores under test are derived
// from it rather than typed: the claim is the banding, not the number.
const KNOWN_CODE = 141746;

function expected(): number {
  const published = projectionFor(KNOWN_CODE);
  if (!published) throw new Error("the artifact no longer knows the test code");
  return published.expectedPoints;
}

function pick(squadPosition: number, over: Partial<PublicTeamPick> = {}) {
  return {
    elementId: 100 + squadPosition,
    squadPosition,
    multiplier: squadPosition <= 11 ? 1 : 0,
    isCaptain: false,
    isViceCaptain: false,
    identity: {
      webName: `Player ${String(squadPosition)}`,
      positionCode: squadPosition === 1 ? "GKP" : "MID",
      teamShortName: "MUN",
      priceTenths: 50,
      code: KNOWN_CODE,
    },
    ...over,
  } satisfies PublicTeamPick;
}

function squad(): PublicTeamPick[] {
  return Array.from({ length: 15 }, (_, index) => pick(index + 1));
}

interface Stat {
  minutes?: number;
  goals_scored?: number;
  assists?: number;
  clean_sheets?: number;
  bonus?: number;
  defensive_contribution?: number;
  total_points?: number;
}

function serve(rows: Record<number, Stat>) {
  const elements = Object.entries(rows).map(([id, stats]) => ({
    id: Number(id),
    stats,
  }));
  const fetchApi = vi.fn(
    () =>
      Promise.resolve(
        new Response(JSON.stringify({ elements }), { status: 200 }),
      ) as Promise<Response>,
  );
  vi.stubGlobal("fetch", fetchApi);
  return fetchApi;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LiveSquad", () => {
  it("splits the fifteen into the eleven and the bench", async () => {
    serve({ 101: { minutes: 90, total_points: 2 } });

    render(<LiveSquad event={7} picks={squad()} />);

    await screen.findByText(/points on the field/i);
    const lists = screen.getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(lists[0]?.querySelectorAll("li")).toHaveLength(11);
    expect(lists[1]?.querySelectorAll("li")).toHaveLength(4);
  });

  it("totals only the eleven, and only what was published", async () => {
    serve({
      101: { minutes: 90, total_points: 6 },
      102: { minutes: 90, total_points: 4 },
      112: { minutes: 90, total_points: 9 },
    });

    render(<LiveSquad event={7} picks={squad()} />);

    expect(await screen.findByText(/points on the field/i)).toHaveTextContent(
      "10 points on the field",
    );
  });

  it("doubles a captain's score into the total", async () => {
    serve({ 101: { minutes: 90, total_points: 6 } });
    const picks = squad();
    picks[0] = pick(1, { isCaptain: true, multiplier: 2 });

    render(<LiveSquad event={7} picks={picks} />);

    expect(await screen.findByText(/points on the field/i)).toHaveTextContent(
      "12 points on the field",
    );
  });

  it("says a score is below what was projected", async () => {
    const floor = Math.max(0, Math.floor(expected() - 2));
    serve({ 101: { minutes: 90, total_points: floor } });

    render(<LiveSquad event={7} picks={squad()} />);

    await waitFor(() => {
      expect(screen.getAllByText(/below/).length).toBeGreaterThan(0);
    });
  });

  it("calls a score that doubles the projection a haul, and marks it", async () => {
    serve({
      101: { minutes: 90, total_points: Math.ceil(expected() * 2) + 8 },
    });

    render(<LiveSquad event={7} picks={squad()} />);

    expect(
      await screen.findByRole("img", { name: "Haul" }),
    ).toBeInTheDocument();
  });

  it("refuses a haul to a small score however far past the projection", async () => {
    serve({ 101: { minutes: 90, total_points: 2 } });

    render(<LiveSquad event={7} picks={squad()} />);

    await screen.findByText(/points on the field/i);
    expect(screen.queryByRole("img", { name: "Haul" })).not.toBeInTheDocument();
  });

  it("draws what a player did rather than listing it", async () => {
    serve({
      101: {
        assists: 1,
        bonus: 3,
        clean_sheets: 1,
        goals_scored: 2,
        minutes: 90,
        total_points: 16,
      },
    });

    render(<LiveSquad event={7} picks={squad()} />);

    expect(await screen.findAllByRole("img", { name: "Goal" })).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Assist" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Clean sheet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Three bonus points" }),
    ).toBeInTheDocument();
  });

  it("withholds a clean sheet from a player who did not play the hour", async () => {
    serve({ 101: { clean_sheets: 1, minutes: 20, total_points: 1 } });

    render(<LiveSquad event={7} picks={squad()} />);

    await screen.findByText(/points on the field/i);
    expect(
      screen.queryByRole("img", { name: "Clean sheet" }),
    ).not.toBeInTheDocument();
  });

  it("holds a midfielder to the midfield defensive bar", async () => {
    serve({
      102: { defensive_contribution: 12, minutes: 90, total_points: 4 },
      103: { defensive_contribution: 11, minutes: 90, total_points: 2 },
    });

    render(<LiveSquad event={7} picks={squad()} />);

    await screen.findByText(/points on the field/i);
    expect(
      screen.getAllByRole("img", { name: "Defensive contribution" }),
    ).toHaveLength(1);
  });

  it("names the players the gameweek published no score for", async () => {
    serve({ 101: { minutes: 90, total_points: 2 } });

    render(<LiveSquad event={7} picks={squad()} />);

    await screen.findByText(/points on the field/i);
    expect(screen.getAllByText(/no score published/)).toHaveLength(14);
  });

  it("says the scores could not be read rather than showing zeroes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("", { status: 404 }))),
    );

    render(<LiveSquad event={7} picks={squad()} />);

    expect(await screen.findByRole("status")).toHaveTextContent(/404/);
    expect(screen.queryByText(/points on the field/i)).not.toBeInTheDocument();
  });

  it("reads a settled bundled score when the deployed proxy route is missing", async () => {
    const fetchApi = vi.fn<typeof fetch>().mockImplementation((input) =>
      Promise.resolve(
        String(input) === "/live/2026-27/gw02.json"
          ? Response.json({
              elements: [{ id: 101, stats: { minutes: 90, total_points: 6 } }],
            })
          : new Response("", { status: 404 }),
      ),
    );

    const live = await fetchLiveGameweek(2, fetchApi);

    expect(live.players.get(101)?.totalPoints).toBe(6);
    expect(fetchApi).toHaveBeenCalledWith(
      "/live/2026-27/gw02.json",
      expect.anything(),
    );
  });

  it("still fails visibly when no settled bundled score exists", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("", { status: 404 }));

    await expect(fetchLiveGameweek(3, fetchApi)).rejects.toMatchObject({
      reason: "unreachable",
      message: "FPL returned 404 for the gameweek's scores",
    });
  });

  it("retries a score that failed before its settled fallback arrived", async () => {
    let available = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          available
            ? Response.json({
                elements: [
                  { id: 101, stats: { minutes: 90, total_points: 6 } },
                ],
              })
            : new Response("", { status: 404 }),
        ),
      ),
    );
    render(<LiveSquad event={2} picks={squad()} />);

    const retry = await screen.findByRole("button", { name: "Try again" });
    available = true;
    retry.click();

    expect(await screen.findByText(/points on the field/i)).toHaveTextContent(
      "6 points on the field",
    );
  });

  it("does not show one gameweek's scores under another's heading", async () => {
    serve({ 101: { minutes: 90, total_points: 6 } });
    const { rerender } = render(<LiveSquad event={7} picks={squad()} />);
    await screen.findByText(/points on the field/i);

    serve({ 101: { minutes: 90, total_points: 3 } });
    rerender(<LiveSquad event={8} picks={squad()} />);

    // The week before is dropped the moment the heading changes, not left up
    // until the new one answers.
    expect(screen.queryByText(/points on the field/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/points on the field/i)).toHaveTextContent(
      "3 points on the field",
    );
  });
});
