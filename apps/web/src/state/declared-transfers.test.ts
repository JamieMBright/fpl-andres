import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  forgetDeclaredTransfers,
  readDeclaredTransfers,
  recordAnalysisRequest,
  saveDeclaredTransfer,
  squadAfterDeclared,
  type DeclaredTransfer,
} from "./declared-transfers";

/**
 * A manager's picks are private until the deadline, so between a transfer and
 * that deadline the public squad is stale. These pin the two things that keeps
 * honest: his own browser is the only source the plan reads, and a declaration
 * can never leave him with fourteen players.
 */

function memoryStorage(): Storage {
  const held = new Map<string, string>();
  return {
    get length() {
      return held.size;
    },
    clear: () => held.clear(),
    getItem: (key) => held.get(key) ?? null,
    key: (index) => [...held.keys()][index] ?? null,
    removeItem: (key) => held.delete(key),
    setItem: (key, value) => held.set(key, value),
  } as Storage;
}

const SWAP: DeclaredTransfer = {
  event: 5,
  elementOut: 100,
  elementIn: 200,
  pointsCharged: 0,
};

describe("declared transfers", () => {
  let storage: Storage;

  beforeEach(() => {
    storage = memoryStorage();
  });

  it("remembers what a manager said he did", () => {
    saveDeclaredTransfer(storage, 42, SWAP);

    expect(readDeclaredTransfers(storage, 42, 5)).toEqual([SWAP]);
  });

  it("keeps one manager's declaration away from another's", () => {
    saveDeclaredTransfer(storage, 42, SWAP);

    expect(readDeclaredTransfers(storage, 43, 5)).toEqual([]);
  });

  it("drops a declaration for a gameweek that has already been published", () => {
    saveDeclaredTransfer(storage, 42, SWAP);

    // Once FPL shows gameweek 5, the override is spent rather than wrong.
    expect(readDeclaredTransfers(storage, 42, 6)).toEqual([]);
  });

  it("does not record the same swap twice", () => {
    saveDeclaredTransfer(storage, 42, SWAP);
    saveDeclaredTransfer(storage, 42, SWAP);

    expect(readDeclaredTransfers(storage, 42, 5)).toHaveLength(1);
  });

  it("survives a storage value that is not a declaration", () => {
    storage.setItem("fpl-andres:declared:42", "{ not json");

    expect(readDeclaredTransfers(storage, 42, 1)).toEqual([]);
  });

  it("clears unparseable storage rather than re-reading it forever", () => {
    // Audit item E4. Every other reader in this directory removes the key when
    // the schema refuses it. This one returned [] and left the value in place,
    // so the same corrupt string was parsed on every render until the next
    // write happened to overwrite it.
    storage.setItem("fpl-andres:declared:42", "{ not json");
    readDeclaredTransfers(storage, 42, 1);

    expect(storage.getItem("fpl-andres:declared:42")).toBeNull();
  });

  it("clears valid JSON that is not a declaration", () => {
    storage.setItem(
      "fpl-andres:declared:42",
      JSON.stringify({ event: "five" }),
    );
    readDeclaredTransfers(storage, 42, 1);

    expect(storage.getItem("fpl-andres:declared:42")).toBeNull();
  });

  it("leaves a good value alone", () => {
    saveDeclaredTransfer(storage, 42, SWAP);
    readDeclaredTransfers(storage, 42, 9);

    // Spent for gameweek 9, but still the manager's record of gameweek 5.
    expect(storage.getItem("fpl-andres:declared:42")).not.toBeNull();
  });

  it("forgets everything for one manager on request", () => {
    saveDeclaredTransfer(storage, 42, SWAP);
    forgetDeclaredTransfers(storage, 42);

    expect(readDeclaredTransfers(storage, 42, 1)).toEqual([]);
  });
});

describe("applying a declaration to the published squad", () => {
  it("puts the new player where the old one was", () => {
    expect(squadAfterDeclared([1, 100, 3], [SWAP])).toEqual([1, 200, 3]);
  });

  it("keeps the squad at fifteen when the player named is not owned", () => {
    const squad = Array.from({ length: 15 }, (_, index) => index + 1);

    const after = squadAfterDeclared(squad, [
      { event: 5, elementOut: 999, elementIn: 200, pointsCharged: 0 },
    ]);

    expect(after).toHaveLength(15);
    expect(after).not.toContain(200);
  });

  it("refuses a swap that would own the same player twice", () => {
    const after = squadAfterDeclared(
      [1, 100, 200],
      [{ event: 5, elementOut: 100, elementIn: 200, pointsCharged: 0 }],
    );

    expect(after).toEqual([1, 100, 200]);
  });

  it("applies several declarations in order", () => {
    const after = squadAfterDeclared(
      [1, 2, 3],
      [
        { event: 5, elementOut: 1, elementIn: 11, pointsCharged: 0 },
        { event: 5, elementOut: 2, elementIn: 12, pointsCharged: 4 },
      ],
    );

    expect(after).toEqual([11, 12, 3]);
  });
});

describe("recording the request", () => {
  it("posts the declaration without waiting for it", () => {
    const fetchApi = vi.fn().mockResolvedValue(new Response(null));

    recordAnalysisRequest(
      { season: "2026-27", entryId: 42, event: 5, transfer: SWAP },
      fetchApi as unknown as typeof fetch,
    );

    expect(fetchApi).toHaveBeenCalledWith(
      "/api/analysis-request",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("never throws when recording fails, because a plan does not depend on it", () => {
    const fetchApi = vi.fn().mockRejectedValue(new Error("offline"));

    expect(() => {
      recordAnalysisRequest(
        { season: "2026-27", entryId: 42, event: 5, transfer: null },
        fetchApi as unknown as typeof fetch,
      );
    }).not.toThrow();
  });
});
