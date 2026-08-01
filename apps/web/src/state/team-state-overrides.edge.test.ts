import { describe, expect, it } from "vitest";

import {
  loadTeamStateOverrides,
  removeTeamStateOverrides,
  saveTeamStateOverrides,
  teamStateOverridesStorageKey,
} from "./team-state-overrides";

/**
 * Audit item #164. The override cache lives in localStorage, which is the least
 * reliable store the app touches: it is shared with every other tab, capped at a
 * few megabytes, and can be edited by hand in devtools.
 *
 * The failure that matters is not losing an override — that is recoverable by
 * re-entering it. It is *showing the wrong one*: an override for a different
 * entry, or one made against a state the manager has since changed.
 */

const DEADLINE = "2026-08-21T17:30:00Z";

function overrides(basedOn = DEADLINE) {
  return {
    source: "manager" as const,
    basedOnStateAsOf: basedOn,
    updatedAt: basedOn,
    bankTenths: 12,
    availableFreeTransfers: 2,
    currentSquad: null,
    queuedTransfers: null,
    availableChips: null,
  };
}

class MemoryStorage implements Storage {
  private readonly entries = new Map<string, string>();
  quotaAfter = Number.POSITIVE_INFINITY;

  get length(): number {
    return this.entries.size;
  }
  key(index: number): string | null {
    return [...this.entries.keys()][index] ?? null;
  }
  getItem(key: string): string | null {
    return this.entries.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    if (this.entries.size >= this.quotaAfter) {
      const error = new DOMException("quota exceeded", "QuotaExceededError");
      throw error;
    }
    this.entries.set(key, value);
  }
  removeItem(key: string): void {
    this.entries.delete(key);
  }
  clear(): void {
    this.entries.clear();
  }
}

describe("override storage edge cases", () => {
  it("round-trips a valid override", () => {
    const storage = new MemoryStorage();

    saveTeamStateOverrides(storage, 212279, overrides());

    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toEqual(
      overrides(),
    );
  });

  it("ignores an override saved against a different deadline", () => {
    // The manager has made a transfer since. An override built on the old state
    // would apply a bank balance that no longer exists.
    const storage = new MemoryStorage();
    saveTeamStateOverrides(storage, 212279, overrides("2026-08-14T17:30:00Z"));

    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toBeNull();
  });

  it("never returns another entry's override", () => {
    const storage = new MemoryStorage();
    saveTeamStateOverrides(storage, 111111, overrides());

    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toBeNull();
  });

  it("discards a corrupted entry rather than throwing", () => {
    const storage = new MemoryStorage();
    storage.setItem(
      teamStateOverridesStorageKey(212279, DEADLINE),
      "{not json at all",
    );

    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toBeNull();
    // And clears it, so the next read is not the same failure again.
    expect(
      storage.getItem(teamStateOverridesStorageKey(212279, DEADLINE)),
    ).toBeNull();
  });

  it("discards an entry that parses but does not match the contract", () => {
    const storage = new MemoryStorage();
    storage.setItem(
      teamStateOverridesStorageKey(212279, DEADLINE),
      JSON.stringify({ basedOnStateAsOf: DEADLINE, bankTenths: "lots" }),
    );

    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toBeNull();
  });

  it("discards an entry whose own timestamp disagrees with its key", () => {
    // Hand-edited devtools, or a key format change. The value is authoritative.
    const storage = new MemoryStorage();
    storage.setItem(
      teamStateOverridesStorageKey(212279, DEADLINE),
      JSON.stringify(overrides("2020-01-01T00:00:00Z")),
    );

    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toBeNull();
  });

  it("keeps only the newest override for an entry", () => {
    // Otherwise every deadline leaves a row behind and the quota fills with
    // states nobody can use.
    const storage = new MemoryStorage();

    saveTeamStateOverrides(storage, 212279, overrides("2026-08-14T17:30:00Z"));
    saveTeamStateOverrides(storage, 212279, overrides());

    expect(storage.length).toBe(1);
    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toEqual(
      overrides(),
    );
  });

  it("does not prune another entry's override while saving", () => {
    const storage = new MemoryStorage();
    saveTeamStateOverrides(storage, 111111, overrides());

    saveTeamStateOverrides(storage, 212279, overrides());

    expect(loadTeamStateOverrides(storage, 111111, DEADLINE)).toEqual(
      overrides(),
    );
  });

  it("refuses to save something that is not a valid override", () => {
    const storage = new MemoryStorage();

    expect(() =>
      saveTeamStateOverrides(storage, 212279, { bankTenths: -5 }),
    ).toThrow();
    expect(storage.length).toBe(0);
  });

  it("removing an override leaves the store clean", () => {
    const storage = new MemoryStorage();
    saveTeamStateOverrides(storage, 212279, overrides());

    removeTeamStateOverrides(storage, 212279, DEADLINE);

    expect(storage.length).toBe(0);
    expect(loadTeamStateOverrides(storage, 212279, DEADLINE)).toBeNull();
  });

  it("surfaces a full quota rather than silently dropping the override", () => {
    // The caller has to know. An override that looks saved and is not is worse
    // than one that visibly failed, because the manager plans around it.
    const storage = new MemoryStorage();
    storage.quotaAfter = 0;

    expect(() => saveTeamStateOverrides(storage, 212279, overrides())).toThrow(
      /quota/i,
    );
  });
});
