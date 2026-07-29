import { describe, expect, it } from "vitest";

import entryCases from "../fixtures/fpl-entry-cases.json";
import sourceCases from "../fixtures/source-snapshot-cases.json";
import {
  fplEntrySchema,
  parseSourceSnapshot,
  sourceSnapshotSchema,
} from "./index";

describe("shared FPL contracts", () => {
  it("matches the shared cross-language source snapshot corpus", () => {
    for (const valid of sourceCases.valid) {
      expect(() => sourceSnapshotSchema.parse(valid)).not.toThrow();
    }
    for (const invalid of sourceCases.invalid) {
      expect(() => sourceSnapshotSchema.parse(invalid)).toThrow();
    }
  });

  it("matches the shared cross-language entry corpus", () => {
    for (const valid of entryCases.valid) {
      expect(() => fplEntrySchema.parse(valid)).not.toThrow();
    }
    for (const invalid of entryCases.invalid) {
      expect(() => fplEntrySchema.parse(invalid)).toThrow();
    }
  });

  it("preserves explicit pre-season unknown team state", () => {
    const entry = fplEntrySchema.parse({
      id: 1,
      name: "First Entry",
      startedEvent: 1,
      currentEvent: null,
      lastDeadlineBank: null,
      lastDeadlineValue: null,
      lastDeadlineTotalTransfers: 0,
    });

    expect(entry.currentEvent).toBeNull();
    expect(entry.lastDeadlineBank).toBeNull();
    expect(entry.lastDeadlineValue).toBeNull();
  });

  it("rejects invalid public entry state instead of coercing it", () => {
    expect(() =>
      fplEntrySchema.parse({
        id: 0,
        name: "Invalid",
        startedEvent: 1,
        currentEvent: null,
        lastDeadlineBank: -1,
        lastDeadlineValue: null,
        lastDeadlineTotalTransfers: 0,
      }),
    ).toThrow();
  });

  it("normalizes content hashes and rejects impossible source chronology", () => {
    const snapshot = parseSourceSnapshot({
      source: "fpl",
      fetchedAt: "2026-07-29T18:00:00Z",
      dataAvailableAt: "2026-07-29T17:59:00Z",
      contentHash: `sha256:${"A".repeat(64)}`,
      upstreamReference: "https://fantasy.premierleague.com/api/entry/1/",
    });
    expect(snapshot.contentHash).toBe(`sha256:${"a".repeat(64)}`);

    expect(() =>
      sourceSnapshotSchema.parse({
        ...snapshot,
        dataAvailableAt: "2026-07-29T18:01:00Z",
      }),
    ).toThrow("dataAvailableAt cannot be later than fetchedAt");
  });
});
