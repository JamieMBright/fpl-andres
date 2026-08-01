import { beforeEach, describe, expect, it } from "vitest";

import {
  loadTeamStateOverrides,
  saveTeamStateOverrides,
  TeamStateOverridesConflictError,
} from "./team-state-overrides";

/**
 * Audit item #66.
 *
 * The item filed this against a Python module. There is no write path there --
 * `team_state.py` only resolves -- but the concern is real and lives in this
 * file instead: two tabs open on the same manager, both editing corrections.
 * The second `setItem` wins, the first tab still shows what it saved, and
 * nothing tells anyone the two disagree.
 *
 * The loss is invisible because both writes succeed. That is what makes it
 * worth a precondition rather than a warning.
 */

const DEADLINE = "2026-08-21T17:30:00Z";
const ENTRY_ID = 212_279;

function overrides(updatedAt: string, bankTenths = 12) {
  return {
    source: "manager" as const,
    basedOnStateAsOf: DEADLINE,
    updatedAt,
    bankTenths,
    availableFreeTransfers: 1,
    currentSquad: null,
    queuedTransfers: null,
    availableChips: ["wildcard"],
  };
}

beforeEach(() => {
  localStorage.clear();
});

describe("compare and set", () => {
  it("writes when nothing is stored and the writer expected nothing", () => {
    const saved = saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:00:00.000Z"),
      { expectedUpdatedAt: null },
    );
    expect(saved.bankTenths).toBe(12);
    expect(
      loadTeamStateOverrides(localStorage, ENTRY_ID, DEADLINE)?.bankTenths,
    ).toBe(12);
  });

  it("writes when the stored record is the one the writer was editing", () => {
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:00:00.000Z", 12),
      { expectedUpdatedAt: null },
    );
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:05:00.000Z", 34),
      { expectedUpdatedAt: "2026-08-21T18:00:00.000Z" },
    );
    expect(
      loadTeamStateOverrides(localStorage, ENTRY_ID, DEADLINE)?.bankTenths,
    ).toBe(34);
  });

  it("refuses the write that would lose another tab's correction", () => {
    // Both tabs loaded when nothing was stored. Tab B saves. Tab A then saves
    // its own edit, which without a precondition simply replaces B's.
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:05:00.000Z", 34),
      { expectedUpdatedAt: null },
    );

    expect(() =>
      saveTeamStateOverrides(
        localStorage,
        ENTRY_ID,
        overrides("2026-08-21T18:06:00.000Z", 99),
        { expectedUpdatedAt: null },
      ),
    ).toThrow(TeamStateOverridesConflictError);

    expect(
      loadTeamStateOverrides(localStorage, ENTRY_ID, DEADLINE)?.bankTenths,
    ).toBe(34);
  });

  it("is not fooled by the later write having a newer timestamp", () => {
    // "Newest wins" would accept exactly the write that loses the correction,
    // because the second tab's updatedAt is genuinely newer. The precondition
    // is what the writer believed it was editing, not when it wrote.
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:05:00.000Z", 34),
      { expectedUpdatedAt: null },
    );
    expect(() =>
      saveTeamStateOverrides(
        localStorage,
        ENTRY_ID,
        overrides("2999-01-01T00:00:00.000Z", 99),
        { expectedUpdatedAt: null },
      ),
    ).toThrow(TeamStateOverridesConflictError);
  });

  it("refuses a write whose base has since been removed", () => {
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:00:00.000Z"),
      { expectedUpdatedAt: null },
    );
    localStorage.clear();

    expect(() =>
      saveTeamStateOverrides(
        localStorage,
        ENTRY_ID,
        overrides("2026-08-21T18:05:00.000Z"),
        { expectedUpdatedAt: "2026-08-21T18:00:00.000Z" },
      ),
    ).toThrow(TeamStateOverridesConflictError);
  });

  it("hands the stored record to the caller, so a UI can show what it would replace", () => {
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:05:00.000Z", 34),
      { expectedUpdatedAt: null },
    );
    try {
      saveTeamStateOverrides(
        localStorage,
        ENTRY_ID,
        overrides("2026-08-21T18:06:00.000Z", 99),
        { expectedUpdatedAt: null },
      );
      expect.unreachable();
    } catch (caught) {
      expect(caught).toBeInstanceOf(TeamStateOverridesConflictError);
      expect(
        (caught as TeamStateOverridesConflictError).stored?.bankTenths,
      ).toBe(34);
    }
  });

  it("says what to do rather than what went wrong", () => {
    const error = new TeamStateOverridesConflictError(null);
    expect(error.message).toContain("another tab");
    expect(error.message).toContain("Reload");
  });

  it("validates the payload before consulting the precondition", () => {
    // An invalid payload is the writer's fault whatever the stored record is,
    // and reporting a conflict for it would send someone to look at another tab
    // over a typo.
    expect(() =>
      saveTeamStateOverrides(
        localStorage,
        ENTRY_ID,
        { ...overrides("2026-08-21T18:00:00.000Z"), bankTenths: -5 },
        { expectedUpdatedAt: "something-else" },
      ),
    ).not.toThrow(TeamStateOverridesConflictError);
  });

  it("leaves an unconditional write unconditional", () => {
    // Existing callers that pass no precondition keep the old behaviour. That
    // is deliberate: the check belongs to a caller that knows what it loaded,
    // and a caller that does not know cannot invent an answer.
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:05:00.000Z", 34),
    );
    saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:06:00.000Z", 99),
    );
    expect(
      loadTeamStateOverrides(localStorage, ENTRY_ID, DEADLINE)?.bankTenths,
    ).toBe(99);
  });

  it("treats a corrupt stored record as absent rather than as a conflict", () => {
    const key = `fpl-andres:team-state-overrides:v1:${ENTRY_ID}:${DEADLINE}`;
    localStorage.setItem(key, "{not json");
    const saved = saveTeamStateOverrides(
      localStorage,
      ENTRY_ID,
      overrides("2026-08-21T18:00:00.000Z"),
      { expectedUpdatedAt: null },
    );
    expect(saved.bankTenths).toBe(12);
  });

  it("does not consult another entry's record", () => {
    saveTeamStateOverrides(
      localStorage,
      111_111,
      overrides("2026-08-21T18:05:00.000Z"),
      {
        expectedUpdatedAt: null,
      },
    );
    expect(() =>
      saveTeamStateOverrides(
        localStorage,
        ENTRY_ID,
        overrides("2026-08-21T18:06:00.000Z"),
        { expectedUpdatedAt: null },
      ),
    ).not.toThrow();
  });
});
