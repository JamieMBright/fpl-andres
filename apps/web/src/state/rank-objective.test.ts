import { describe, expect, it } from "vitest";

import {
  NO_OBJECTIVE,
  OBJECTIVES,
  chasesLeague,
  forgetRankObjective,
  readRankObjective,
  saveRankObjective,
} from "./rank-objective";

function store(): Storage {
  const held = new Map<string, string>();
  return {
    get length() {
      return held.size;
    },
    clear: () => {
      held.clear();
    },
    getItem: (key: string) => held.get(key) ?? null,
    key: (index: number) => [...held.keys()][index] ?? null,
    removeItem: (key: string) => {
      held.delete(key);
    },
    setItem: (key: string, value: string) => {
      held.set(key, value);
    },
  };
}

describe("which race the plan is being solved for", () => {
  it("says nothing rather than assuming the commoner answer", () => {
    // Null, not "overall". Guessing would give half the readers the wrong plan
    // with no way to tell it was the wrong question rather than a wrong number.
    expect(readRankObjective(store(), 1)).toBeNull();
  });

  it("returns what was chosen", () => {
    const storage = store();
    saveRankObjective(storage, 1, { objective: "league", leagueId: 34555 });

    expect(readRankObjective(storage, 1)).toEqual({
      objective: "league",
      leagueId: 34555,
    });
  });

  it("keeps one team's answer out of another's", () => {
    const storage = store();
    saveRankObjective(storage, 1, { objective: "league", leagueId: 34555 });

    expect(readRankObjective(storage, 2)).toBeNull();
  });

  it("drops a league nobody is chasing any more", () => {
    const storage = store();
    saveRankObjective(storage, 1, { objective: "league", leagueId: 34555 });

    const saved = saveRankObjective(storage, 1, {
      objective: "overall",
      leagueId: 34555,
    });

    expect(saved.leagueId).toBeNull();
    expect(readRankObjective(storage, 1)?.leagueId).toBeNull();
  });

  it("discards a stored value it cannot trust", () => {
    const storage = store();
    storage.setItem("fpl-andres:objective:v1:1", '{"objective":"mini"}');

    expect(readRankObjective(storage, 1)).toBeNull();
    expect(storage.getItem("fpl-andres:objective:v1:1")).toBeNull();
  });

  it("discards a stored value that is not JSON", () => {
    const storage = store();
    storage.setItem("fpl-andres:objective:v1:1", "{");

    expect(readRankObjective(storage, 1)).toBeNull();
  });

  it("forgets on request", () => {
    const storage = store();
    saveRankObjective(storage, 1, NO_OBJECTIVE);
    forgetRankObjective(storage, 1);

    expect(readRankObjective(storage, 1)).toBeNull();
  });

  it("offers exactly the two races there are", () => {
    expect([...OBJECTIVES]).toEqual(["overall", "league"]);
  });
});

describe("whether a league can be read yet", () => {
  it("refuses an unanswered question", () => {
    expect(chasesLeague(null)).toBe(false);
  });

  it("refuses the overall race", () => {
    expect(chasesLeague({ objective: "overall", leagueId: null })).toBe(false);
  });

  it("refuses a league nobody has named", () => {
    expect(chasesLeague({ objective: "league", leagueId: null })).toBe(false);
  });

  it("accepts a named league", () => {
    expect(chasesLeague({ objective: "league", leagueId: 34555 })).toBe(true);
  });
});
