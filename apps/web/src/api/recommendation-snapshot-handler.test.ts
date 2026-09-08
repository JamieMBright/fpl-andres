import type { VercelRequest, VercelResponse } from "@vercel/node";
import { afterEach, describe, expect, it, vi } from "vitest";

import plan from "../data/season-plan.json";

const upsertRow = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
const readRows = vi.fn<() => Promise<unknown[]>>().mockResolvedValue([]);

vi.mock("../../../../api/_lib/supabase-write.js", () => ({
  readCredentials: () => ({
    url: "https://project.supabase.invalid",
    secret: "not-a-real-secret",
  }),
  readRows,
  upsertRow,
  SupabaseNotConfigured: class SupabaseNotConfigured extends Error {},
}));

const recommendationSnapshotHandler = (
  await import("../../../../api/recommendation-snapshot")
).default;

const week = plan.gameweeks[0];
if (!week) throw new Error("test plan has no gameweeks");

const VALID_BODY = {
  season: plan.season,
  entryId: 212279,
  event: week.event,
  deadline: week.deadline,
  modelVersion: plan.modelVersion,
  starters: week.squadElementIds.slice(0, 11),
  bench: week.squadElementIds.slice(11),
  captain: week.squadElementIds[0],
  viceCaptain: week.squadElementIds[1],
  transferIn: null,
  transferOut: null,
  chip: null,
  projectedPoints: week.projectedPoints,
  netExpectedPoints: week.netExpectedPoints,
  paidTransfers: week.paidTransfers,
  transferCost: week.transferCostPoints,
  confidence: week.confidence,
  recordedAt: "2026-09-08T08:00:00Z",
  sourceReference: "season-plan:8.17",
};

function request(
  overrides: Partial<VercelRequest> & {
    headers?: VercelRequest["headers"];
    query?: VercelRequest["query"];
  } = {},
): VercelRequest {
  const { headers, query, ...requestOverrides } = overrides;
  return {
    method: "POST",
    body: VALID_BODY,
    headers: {
      "content-type": "application/json",
      "content-length": String(Buffer.byteLength(JSON.stringify(VALID_BODY))),
      origin: "https://fpl-andres.vercel.app",
      "x-forwarded-host": "fpl-andres.vercel.app",
      "x-forwarded-proto": "https",
      "x-vercel-forwarded-for": `192.0.2.${Math.floor(Math.random() * 200) + 1}`,
      ...headers,
    },
    query,
    ...requestOverrides,
  } as unknown as VercelRequest;
}

function response(): {
  vercel: VercelResponse;
  status: () => number;
  body: () => unknown;
} {
  let status = 0;
  let body: unknown;
  const vercel = {
    setHeader() {
      return vercel;
    },
    status(next: number) {
      status = next;
      return vercel;
    },
    json(next: unknown) {
      body = next;
      return vercel;
    },
  } as unknown as VercelResponse;
  return { vercel, status: () => status, body: () => body };
}

afterEach(() => {
  upsertRow.mockClear();
  readRows.mockClear();
});

describe("recommendation snapshot boundary", () => {
  it("writes only the validated derived snapshot", async () => {
    const current = response();

    await recommendationSnapshotHandler(request(), current.vercel);

    expect(current.status()).toBe(202);
    expect(upsertRow).toHaveBeenCalledWith(
      "recommendation_snapshots",
      expect.not.objectContaining({
        bank: expect.anything(),
        free_transfers: expect.anything(),
      }),
      ["entry_id", "event"],
      expect.anything(),
    );
  });

  it.each([
    ["event", { event: 5 }],
    ["deadline", { deadline: "2026-09-13T12:30:00Z" }],
    ["model", { modelVersion: "old" }],
    ["player", { starters: [999_999, ...VALID_BODY.starters.slice(1)] }],
  ])("rejects a wrong canonical %s", async (_label, change) => {
    const current = response();

    await recommendationSnapshotHandler(
      request({ body: { ...VALID_BODY, ...change } }),
      current.vercel,
    );

    expect(current.status()).toBe(400);
    expect(upsertRow).not.toHaveBeenCalled();
  });

  it("rejects private fields instead of silently stripping them", async () => {
    const current = response();

    await recommendationSnapshotHandler(
      request({ body: { ...VALID_BODY, bank: 100 } }),
      current.vercel,
    );

    expect(current.status()).toBe(400);
    expect(upsertRow).not.toHaveBeenCalled();
  });

  it("returns only the safe latest snapshot shape", async () => {
    readRows.mockResolvedValueOnce([
      {
        season: VALID_BODY.season,
        entry_id: VALID_BODY.entryId,
        event: VALID_BODY.event,
        deadline: VALID_BODY.deadline,
        model_version: VALID_BODY.modelVersion,
        starters: VALID_BODY.starters,
        bench: VALID_BODY.bench,
        captain: VALID_BODY.captain,
        vice_captain: VALID_BODY.viceCaptain,
        transfer_in: null,
        transfer_out: null,
        chip: null,
        projected_points: VALID_BODY.projectedPoints,
        net_expected_points: VALID_BODY.netExpectedPoints,
        paid_transfers: VALID_BODY.paidTransfers,
        transfer_cost: VALID_BODY.transferCost,
        confidence: VALID_BODY.confidence,
        recorded_at: VALID_BODY.recordedAt,
        source_reference: VALID_BODY.sourceReference,
      },
    ]);
    const current = response();

    await recommendationSnapshotHandler(
      request({ method: "GET", body: undefined, query: { entryId: "212279" } }),
      current.vercel,
    );

    expect(current.status()).toBe(200);
    expect(current.body()).toEqual({ snapshot: VALID_BODY });
    expect(JSON.stringify(current.body())).not.toContain("bank");
  });
});
