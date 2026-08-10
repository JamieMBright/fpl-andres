import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MiniLeagueError,
  RIVAL_LIMIT,
  exposureOf,
  fetchMiniLeague,
  overlookedIn,
  readPicks,
  readStandings,
  threatsIn,
  type MiniLeague,
  type RivalSquad,
} from "./mini-league";

/**
 * A mini-league is a race against squads you can read, so the number that
 * decides a transfer is what the people you are racing hold — not what the
 * whole game holds, and not what the projection says in isolation.
 */

function row(entryId: number) {
  return {
    entryId,
    entryName: `Team ${String(entryId)}`,
    managerName: "A Manager",
    rank: entryId,
    totalPoints: 100 + entryId,
  };
}

function rival(
  entryId: number,
  starters: number[],
  captain: number | null,
  bench: number[] = [],
): RivalSquad {
  return {
    ...row(entryId),
    squad: [...starters, ...bench],
    starters,
    captain,
  };
}

function league(rivals: RivalSquad[], mine: number[]): MiniLeague {
  return {
    leagueId: 1,
    leagueName: "The League",
    event: 7,
    rivals,
    unavailable: [],
    exposure: exposureOf(rivals, mine),
  };
}

describe("reading the standings", () => {
  it("names the league and everyone in it", () => {
    const read = readStandings(9, {
      league: { name: "Sunday Pub" },
      standings: {
        results: [
          {
            entry: 11,
            entry_name: "Alpha",
            player_name: "A",
            rank: 1,
            total: 500,
          },
          {
            entry: 12,
            entry_name: "Beta",
            player_name: "B",
            rank: 2,
            total: 480,
          },
        ],
      },
    });

    expect(read.leagueName).toBe("Sunday Pub");
    expect(read.rows.map((entry) => entry.entryId)).toEqual([11, 12]);
    expect(read.rows[0]?.entryName).toBe("Alpha");
  });

  it("refuses a payload that is not the shape FPL publishes", () => {
    expect(() => readStandings(9, { league: { name: "x" } })).toThrow(
      MiniLeagueError,
    );
  });

  it("says the league is empty rather than reporting nobody owns anybody", () => {
    expect(() =>
      readStandings(9, { league: { name: "x" }, standings: { results: [] } }),
    ).toThrow(/no standings/);
  });
});

describe("reading a rival's gameweek", () => {
  it("keeps the eleven apart from the fifteen", () => {
    const read = readPicks(row(11), {
      picks: [
        { element: 1, multiplier: 2, is_captain: true },
        { element: 2, multiplier: 1, is_captain: false },
        { element: 3, multiplier: 0, is_captain: false },
      ],
    });

    expect(read.squad).toEqual([1, 2, 3]);
    expect(read.starters).toEqual([1, 2]);
    expect(read.captain).toBe(1);
  });

  it("refuses a squad that names nobody", () => {
    expect(() => readPicks(row(11), { picks: [] })).toThrow(MiniLeagueError);
  });
});

describe("what the league is exposed to", () => {
  it("counts a starter and ignores a bench", () => {
    const spread = exposureOf([rival(11, [1], null, [2])], []);

    expect(spread.find((entry) => entry.elementId === 1)?.ownedShare).toBe(1);
    expect(spread.find((entry) => entry.elementId === 2)).toBeUndefined();
  });

  it("counts a captain twice, because he scores twice", () => {
    const spread = exposureOf([rival(11, [1, 2], 1)], []);

    expect(spread.find((entry) => entry.elementId === 1)?.effective).toBe(2);
    expect(spread.find((entry) => entry.elementId === 2)?.effective).toBe(1);
  });

  it("measures a share against the squads it actually read", () => {
    const spread = exposureOf(
      [rival(11, [1], null), rival(12, [1], null), rival(13, [2], null)],
      [],
    );

    expect(
      spread.find((entry) => entry.elementId === 1)?.ownedShare,
    ).toBeCloseTo(2 / 3);
  });

  it("puts the most exposed name first", () => {
    const spread = exposureOf(
      [rival(11, [1, 2], 1), rival(12, [1, 3], null)],
      [],
    );

    expect(spread[0]?.elementId).toBe(1);
  });

  it("keeps a player of yours on the board even where nobody else has him", () => {
    const spread = exposureOf([rival(11, [1], null)], [9]);
    const held = spread.find((entry) => entry.elementId === 9);

    expect(held?.mine).toBe(true);
    expect(held?.effective).toBe(0);
  });
});

describe("the two boards", () => {
  it("calls what they hold and you do not a threat", () => {
    const board = threatsIn(league([rival(11, [1, 2], 1)], [2]));

    expect(board.map((entry) => entry.elementId)).toEqual([1]);
  });

  it("leaves out a name nobody in the league starts", () => {
    const board = threatsIn(league([rival(11, [1], null)], []));

    expect(board.every((entry) => entry.effective > 0)).toBe(true);
  });

  it("puts your least-held player at the top of the other board", () => {
    const board = overlookedIn(
      league([rival(11, [1, 2], null), rival(12, [1], null)], [1, 2, 3]),
    );

    // 3 is held by nobody, 2 by half of them, 1 by all of them.
    expect(board.map((entry) => entry.elementId)).toEqual([3, 2, 1]);
  });
});

describe("fetching a league", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function serve(handler: (url: string) => Response) {
    const api = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(handler(String(input))),
    );
    vi.stubGlobal("fetch", api);
    return api;
  }

  const standings = (count: number) =>
    JSON.stringify({
      league: { name: "The League" },
      standings: {
        results: Array.from({ length: count }, (_unused, index) => ({
          entry: 100 + index,
          entry_name: `Team ${String(index)}`,
          player_name: "A Manager",
          rank: index + 1,
          total: 500 - index,
        })),
      },
    });

  const picks = JSON.stringify({
    picks: [
      { element: 1, multiplier: 2, is_captain: true },
      { element: 2, multiplier: 1, is_captain: false },
    ],
  });

  it("reads the standings and then every squad in them", async () => {
    serve((url) =>
      url.includes("standings")
        ? new Response(standings(2), { status: 200 })
        : new Response(picks, { status: 200 }),
    );

    const read = await fetchMiniLeague(1, 7, [2]);

    expect(read.rivals).toHaveLength(2);
    expect(read.leagueName).toBe("The League");
    expect(threatsIn(read).map((entry) => entry.elementId)).toEqual([1]);
  });

  it("stops at the top of a table too long to read", async () => {
    const api = serve((url) =>
      url.includes("standings")
        ? new Response(standings(200), { status: 200 })
        : new Response(picks, { status: 200 }),
    );

    const read = await fetchMiniLeague(1, 7, []);

    expect(read.rivals).toHaveLength(RIVAL_LIMIT);
    // One standings call plus one per rival read, and no more.
    expect(api).toHaveBeenCalledTimes(RIVAL_LIMIT + 1);
  });

  it("names a squad it could not read instead of dropping it silently", async () => {
    let asked = 0;
    serve((url) => {
      if (url.includes("standings"))
        return new Response(standings(2), { status: 200 });
      asked += 1;
      return asked === 1
        ? new Response("", { status: 404 })
        : new Response(picks, { status: 200 });
    });

    const read = await fetchMiniLeague(1, 7, []);

    expect(read.unavailable).toHaveLength(1);
    expect(read.rivals).toHaveLength(1);
  });

  it("says the deadline has not passed rather than showing an empty league", async () => {
    serve((url) =>
      url.includes("standings")
        ? new Response(standings(2), { status: 200 })
        : new Response("", { status: 404 }),
    );

    await expect(fetchMiniLeague(1, 7, [])).rejects.toThrow(/deadline/);
  });

  it("says so when the league itself cannot be reached", async () => {
    serve(() => new Response("", { status: 404 }));

    await expect(fetchMiniLeague(1, 7, [])).rejects.toThrow(MiniLeagueError);
  });
});
