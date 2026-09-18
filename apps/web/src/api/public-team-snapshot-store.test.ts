import { publicTeamStateSchema } from "@fpl-andres/contracts";
import { describe, expect, it, vi } from "vitest";

import { PublicTeamSnapshotStore } from "../../../../api/_lib/public-team-snapshot-store";
import cases from "../../../../packages/contracts/fixtures/public-team-state-cases.json";

const state = publicTeamStateSchema.parse({
  ...cases.valid[0],
  stateAsOf: "2026-09-18T17:30:00Z",
  dataAvailableAt: "2026-09-18T18:00:00Z",
});
const credentials = { url: "https://cache.example", secret: "test-only" };

function database() {
  const rows: Record<string, unknown>[] = [];
  const fetchApi = vi.fn<typeof fetch>(async (_url, init) => {
    if (init?.method === "POST") {
      rows.splice(0, rows.length, JSON.parse(String(init.body)));
      return new Response(null, { status: 201 });
    }
    return Response.json(rows);
  });
  return { rows, fetchApi };
}

describe("durable public snapshots", () => {
  it("survives a new instance and retains original observation timestamps", async () => {
    const { fetchApi, rows } = database();
    const now = () => Date.parse("2026-09-18T18:01:00Z");
    await new PublicTeamSnapshotStore(credentials, fetchApi, now).write(state);
    const recovered = await new PublicTeamSnapshotStore(
      credentials,
      fetchApi,
      now,
    ).read(123);
    expect(recovered).toEqual(state);
    expect(rows[0]?.captured_at).toBe(state.dataAvailableAt);
    expect(
      fetchApi.mock.calls.every(
        ([, init]) => init?.signal instanceof AbortSignal,
      ),
    ).toBe(true);
  });

  it("refuses an expired snapshot at the next deadline", async () => {
    const { fetchApi } = database();
    const writer = new PublicTeamSnapshotStore(credentials, fetchApi, () =>
      Date.parse("2026-09-18T18:01:00Z"),
    );
    await writer.write(state);
    const reader = new PublicTeamSnapshotStore(credentials, fetchApi, () =>
      Date.parse("2026-10-10T10:00:00Z"),
    );
    expect(await reader.read(123)).toBeNull();
  });

  it.each(["entry_id", "season", "context_hash", "expires_at"])(
    "rejects mismatched %s",
    async (field) => {
      const { fetchApi, rows } = database();
      const store = new PublicTeamSnapshotStore(credentials, fetchApi, () =>
        Date.parse("2026-09-18T18:01:00Z"),
      );
      await store.write(state);
      rows[0]![field] = "wrong";
      expect(await store.read(123)).toBeNull();
    },
  );

  it("never writes manager corrections or invalid state", async () => {
    const { fetchApi } = database();
    const store = new PublicTeamSnapshotStore(credentials, fetchApi);
    await store.write({ ...state, evidenceLevel: "inferred" } as never);
    expect(fetchApi).not.toHaveBeenCalled();
  });

  it("degrades harmlessly when persistence is unavailable", async () => {
    const fetchApi = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("offline"));
    const store = new PublicTeamSnapshotStore(credentials, fetchApi, () =>
      Date.parse("2026-09-18T18:01:00Z"),
    );
    await expect(store.write(state)).resolves.toBeUndefined();
    expect(await store.read(123)).toBeNull();
  });
});
