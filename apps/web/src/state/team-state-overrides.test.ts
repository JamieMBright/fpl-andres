import { beforeEach, describe, expect, it } from "vitest";

import overrideCases from "../../../../packages/contracts/fixtures/team-state-overrides-cases.json";
import {
  loadTeamStateOverrides,
  saveTeamStateOverrides,
  teamStateOverridesStorageKey,
} from "./team-state-overrides";

const ENTRY_ID = 123;
const DEADLINE = "2026-09-12T10:30:00Z";

describe("manager team-state override storage", () => {
  beforeEach(() => localStorage.clear());

  it("round-trips only against the exact entry and public deadline", () => {
    const overrides = overrideCases.valid[0];

    saveTeamStateOverrides(localStorage, ENTRY_ID, overrides);

    expect(loadTeamStateOverrides(localStorage, ENTRY_ID, DEADLINE)).toEqual(
      overrides,
    );
    expect(
      loadTeamStateOverrides(localStorage, ENTRY_ID, "2026-09-19T10:30:00Z"),
    ).toBeNull();
    expect(loadTeamStateOverrides(localStorage, 999, DEADLINE)).toBeNull();
  });

  it("deletes malformed or deadline-mismatched stored state", () => {
    const key = teamStateOverridesStorageKey(ENTRY_ID, DEADLINE);
    localStorage.setItem(key, JSON.stringify({ source: "manager" }));

    expect(loadTeamStateOverrides(localStorage, ENTRY_ID, DEADLINE)).toBeNull();
    expect(localStorage.getItem(key)).toBeNull();

    localStorage.setItem(
      key,
      JSON.stringify({
        ...overrideCases.valid[0],
        basedOnStateAsOf: "2026-09-19T10:30:00Z",
      }),
    );
    expect(loadTeamStateOverrides(localStorage, ENTRY_ID, DEADLINE)).toBeNull();
    expect(localStorage.getItem(key)).toBeNull();
  });

  it("rejects invalid entry IDs before touching storage", () => {
    expect(() => teamStateOverridesStorageKey(0, DEADLINE)).toThrow("entry ID");
    expect(() => teamStateOverridesStorageKey(1.5, DEADLINE)).toThrow(
      "entry ID",
    );
  });
});
