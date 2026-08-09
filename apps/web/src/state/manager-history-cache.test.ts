import { describe, expect, it, beforeEach } from "vitest";

import {
  loadManagerHistory,
  managerHistoryStorageKey,
  saveManagerHistory,
} from "./manager-history-cache";

const ENTRY_ID = 212_279;
const PAYLOAD = {
  current: [{ event: 1, points: 60 }],
  past: [
    {
      season_name: "2010/11",
      total_points: 1963,
      rank: 142_800,
      rank_percentage: "6",
    },
    {
      season_name: "2024/25",
      total_points: 2502,
      rank: 120_612,
      rank_percentage: "2",
    },
  ],
};

describe("the manager history a reader already has", () => {
  beforeEach(() => localStorage.clear());

  it("keeps the settled seasons and nothing about the live one", () => {
    saveManagerHistory(localStorage, ENTRY_ID, PAYLOAD);

    const held = loadManagerHistory(localStorage, ENTRY_ID);

    // The schema coerces FPL's stringified percentage, so what comes back is
    // what the profile reads, not a byte copy of what FPL sent.
    expect(held).toEqual({
      past: [
        {
          season_name: "2010/11",
          total_points: 1963,
          rank: 142_800,
          rank_percentage: 6,
        },
        {
          season_name: "2024/25",
          total_points: 2502,
          rank: 120_612,
          rank_percentage: 2,
        },
      ],
    });
    expect(JSON.stringify(held)).not.toContain("current");
  });

  it("has nothing for a manager it has never seen", () => {
    saveManagerHistory(localStorage, ENTRY_ID, PAYLOAD);

    expect(loadManagerHistory(localStorage, 1)).toBeNull();
  });

  it("drops a copy that no longer matches the shape it is read through", () => {
    const key = managerHistoryStorageKey(ENTRY_ID);
    localStorage.setItem(key, JSON.stringify({ past: "not a list" }));

    expect(loadManagerHistory(localStorage, ENTRY_ID)).toBeNull();
    expect(localStorage.getItem(key)).toBeNull();
  });

  it("survives a value that is not JSON at all", () => {
    const key = managerHistoryStorageKey(ENTRY_ID);
    localStorage.setItem(key, "{not json");

    expect(loadManagerHistory(localStorage, ENTRY_ID)).toBeNull();
    expect(localStorage.getItem(key)).toBeNull();
  });

  it("holds one manager, so a shared browser does not accumulate strangers", () => {
    saveManagerHistory(localStorage, 1, PAYLOAD);
    saveManagerHistory(localStorage, ENTRY_ID, PAYLOAD);

    expect(loadManagerHistory(localStorage, 1)).toBeNull();
    expect(loadManagerHistory(localStorage, ENTRY_ID)).not.toBeNull();
  });

  it("refuses to store something it could not read back", () => {
    saveManagerHistory(localStorage, ENTRY_ID, { past: [{ nonsense: true }] });

    expect(loadManagerHistory(localStorage, ENTRY_ID)).toBeNull();
  });
});
