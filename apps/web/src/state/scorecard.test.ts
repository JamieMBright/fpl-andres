import { beforeEach, describe, expect, it } from "vitest";

import {
  readScorecard,
  recordCall,
  scorecardStorageKey,
  settleCall,
  tally,
} from "./scorecard";

/**
 * A recommendation nobody checks is an opinion. These pin the two properties
 * that make the check worth anything: the call is fixed before the result, and
 * the result is read from what FPL published rather than from what we hoped.
 */

const ENTRY_ID = 212_279;
const SQUAD = Array.from({ length: 15 }, (_unused, index) => index + 1);

const CALL = {
  event: 3,
  squadBefore: SQUAD,
  elementOut: 4,
  elementIn: 99,
  captain: 7,
};

beforeEach(() => {
  localStorage.clear();
});

describe("recordCall", () => {
  it("keeps a call made before the gameweek", () => {
    recordCall(localStorage, ENTRY_ID, CALL);

    const [held] = readScorecard(localStorage, ENTRY_ID);
    expect(held?.event).toBe(3);
    expect(held?.elementIn).toBe(99);
    expect(held?.settled).toBeNull();
  });

  it("refuses to rewrite a call already made for that gameweek", () => {
    recordCall(localStorage, ENTRY_ID, CALL);
    recordCall(localStorage, ENTRY_ID, { ...CALL, elementIn: 123, captain: 8 });

    const [held] = readScorecard(localStorage, ENTRY_ID);
    expect(held?.elementIn).toBe(99);
    expect(held?.captain).toBe(7);
  });

  it("keeps one manager's calls out of another's", () => {
    recordCall(localStorage, ENTRY_ID, CALL);

    expect(readScorecard(localStorage, 999)).toEqual([]);
  });

  it("discards a store that no longer parses rather than guessing", () => {
    const key = scorecardStorageKey(ENTRY_ID);
    localStorage.setItem(key, JSON.stringify([{ event: "three" }]));

    expect(readScorecard(localStorage, ENTRY_ID)).toEqual([]);
    expect(localStorage.getItem(key)).toBeNull();
  });
});

describe("settleCall", () => {
  it("reads the transfer as the difference between the two fifteens", () => {
    recordCall(localStorage, ENTRY_ID, CALL);
    const played = SQUAD.map((id) => (id === 4 ? 99 : id));

    settleCall(localStorage, ENTRY_ID, 3, played, 7);

    const [held] = readScorecard(localStorage, ENTRY_ID);
    expect(held?.settled?.elementOut).toBe(4);
    expect(held?.settled?.elementIn).toBe(99);
    expect(held?.settled?.captain).toBe(7);
  });

  it("names no transfer when the manager kept his fifteen", () => {
    recordCall(localStorage, ENTRY_ID, CALL);

    settleCall(localStorage, ENTRY_ID, 3, SQUAD, 7);

    const [held] = readScorecard(localStorage, ENTRY_ID);
    expect(held?.settled?.elementOut).toBeNull();
    expect(held?.settled?.elementIn).toBeNull();
  });

  it("names no single transfer for a hit or a chip", () => {
    recordCall(localStorage, ENTRY_ID, CALL);
    const played = SQUAD.map((id) =>
      id === 4 ? 99 : id === 5 ? 101 : id === 6 ? 102 : id,
    );

    settleCall(localStorage, ENTRY_ID, 3, played, 7);

    const [held] = readScorecard(localStorage, ENTRY_ID);
    expect(held?.settled?.elementOut).toBeNull();
    expect(held?.settled?.elementIn).toBeNull();
    // Still settled, so the captain call is still scored.
    expect(held?.settled?.captain).toBe(7);
  });

  it("never settles the same gameweek twice", () => {
    recordCall(localStorage, ENTRY_ID, CALL);
    settleCall(localStorage, ENTRY_ID, 3, SQUAD, 7);

    settleCall(localStorage, ENTRY_ID, 3, SQUAD, 12);

    expect(readScorecard(localStorage, ENTRY_ID)[0]?.settled?.captain).toBe(7);
  });

  it("does nothing for a gameweek no call was made in", () => {
    settleCall(localStorage, ENTRY_ID, 9, SQUAD, 7);

    expect(readScorecard(localStorage, ENTRY_ID)).toEqual([]);
  });
});

describe("tally", () => {
  it("counts only the weeks that have been settled", () => {
    recordCall(localStorage, ENTRY_ID, CALL);
    recordCall(localStorage, ENTRY_ID, { ...CALL, event: 4 });
    settleCall(
      localStorage,
      ENTRY_ID,
      3,
      SQUAD.map((id) => (id === 4 ? 99 : id)),
      7,
    );

    const counted = tally(readScorecard(localStorage, ENTRY_ID));

    expect(counted).toEqual({
      settled: 1,
      captainAgreed: 1,
      transferAgreed: 1,
    });
  });

  it("counts a different captain as a disagreement", () => {
    recordCall(localStorage, ENTRY_ID, CALL);
    settleCall(localStorage, ENTRY_ID, 3, SQUAD, 12);

    expect(tally(readScorecard(localStorage, ENTRY_ID))).toEqual({
      settled: 1,
      captainAgreed: 0,
      // Advised a swap, made none.
      transferAgreed: 0,
    });
  });
});
