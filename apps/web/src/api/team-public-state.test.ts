import { createHash } from "node:crypto";

import { publicTeamStateSchema } from "@fpl-andres/contracts";
import { describe, expect, it } from "vitest";

import {
  TeamPublicStateContractError,
  assembleTeamPublicState,
} from "../../../../api/_lib/team-public-state";

const encoder = new TextEncoder();
const fetchedAt = "2026-09-12T12:30:00Z";
const stateAsOf = "2026-09-12T10:30:00Z";

function entryBytes(): Uint8Array {
  return encoder.encode(
    JSON.stringify({
      id: 123,
      name: "Public XI",
      started_event: 1,
      current_event: 5,
      last_deadline_bank: 17,
      last_deadline_value: 1004,
      last_deadline_total_transfers: 4,
    }),
  );
}

function picksPayload(): Record<string, unknown> {
  const picks = Array.from({ length: 15 }, (_, index) => ({
    element: 101 + index,
    position: index + 1,
    multiplier: index === 0 ? 2 : index > 10 ? 0 : 1,
    is_captain: index === 0,
    is_vice_captain: index === 1,
  }));
  return {
    active_chip: null,
    entry_history: {
      event: 5,
      bank: 17,
      value: 1004,
      event_transfers: 1,
      event_transfers_cost: 0,
    },
    picks,
  };
}

function picksBytes(
  payload: Record<string, unknown> = picksPayload(),
): Uint8Array {
  return encoder.encode(JSON.stringify(payload));
}

describe("public team state assembler", () => {
  it("validates two exact FPL payloads into the shared public state", () => {
    const rawEntry = entryBytes();
    const rawPicks = picksBytes();

    const state = assembleTeamPublicState({
      entryBytes: rawEntry,
      entryFetchedAt: fetchedAt,
      picksBytes: rawPicks,
      picksFetchedAt: fetchedAt,
      stateAsOf,
    });

    expect(() => publicTeamStateSchema.parse(state)).not.toThrow();
    expect(state).toMatchObject({
      entryId: 123,
      event: 5,
      bankTenths: 17,
      squadValueTenths: 1004,
      eventTransfers: 1,
      eventTransferCostPoints: 0,
      totalTransfers: 4,
      stateAsOf,
      dataAvailableAt: fetchedAt,
      evidenceLevel: "observed",
    });
    expect(state.picks).toHaveLength(15);
    expect(state.sourceHashes).toEqual(
      [rawEntry, rawPicks]
        .map(
          (bytes) =>
            `sha256:${createHash("sha256").update(bytes).digest("hex")}`,
        )
        .sort(),
    );
  });

  it("rejects entry and picks disagreement instead of choosing one value", () => {
    const payload = picksPayload();
    const history = payload.entry_history as Record<string, unknown>;
    history.bank = 18;

    expect(() =>
      assembleTeamPublicState({
        entryBytes: entryBytes(),
        entryFetchedAt: fetchedAt,
        picksBytes: picksBytes(payload),
        picksFetchedAt: fetchedAt,
        stateAsOf,
      }),
    ).toThrowError(
      new TeamPublicStateContractError("entry and picks bank disagree"),
    );
  });

  it("rejects malformed squad bytes and impossible evidence chronology", () => {
    const payload = picksPayload();
    (payload.picks as unknown[]).pop();

    expect(() =>
      assembleTeamPublicState({
        entryBytes: entryBytes(),
        entryFetchedAt: fetchedAt,
        picksBytes: picksBytes(payload),
        picksFetchedAt: fetchedAt,
        stateAsOf,
      }),
    ).toThrow("exactly 15 picks");

    expect(() =>
      assembleTeamPublicState({
        entryBytes: entryBytes(),
        entryFetchedAt: "2026-09-12T10:29:59Z",
        picksBytes: picksBytes(),
        picksFetchedAt: fetchedAt,
        stateAsOf,
      }),
    ).toThrow("cannot predate stateAsOf");
  });
});
