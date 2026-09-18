import { createHash } from "node:crypto";
import {
  publicTeamStateSchema,
  type PublicTeamState,
} from "@fpl-andres/contracts";
import { z } from "zod";

import deadlines from "../../apps/web/src/data/deadlines.json" with { type: "json" };
import inputs from "../../apps/web/src/data/season-inputs.json" with { type: "json" };
import {
  readCredentials,
  readRows,
  upsertRow,
  type SupabaseCredentials,
} from "./supabase-write.js";

const firstYear = new Date(deadlines.deadlines[0]!.deadline).getUTCFullYear();
const season = `${firstYear}-${String(firstYear + 1).slice(-2)}`;
const contextHash = createHash("sha256")
  .update(
    JSON.stringify({
      version: 1,
      deadlines: deadlines.deadlines.map(({ event, deadline }) => [
        event,
        deadline,
      ]),
      players: inputs.players
        .map(({ id, code }) => [id, code])
        .sort((left, right) => left[0]! - right[0]!),
    }),
  )
  .digest("hex");

const rowSchema = z.object({
  season: z.literal(season),
  entry_id: z.int().positive(),
  event: z.int().positive(),
  context_hash: z.literal(contextHash),
  captured_at: z.iso.datetime({ offset: true }),
  expires_at: z.iso.datetime({ offset: true }),
  state: publicTeamStateSchema,
});

export interface TeamSnapshotStore {
  read(entryId: number): Promise<PublicTeamState | null>;
  write(state: PublicTeamState): Promise<void>;
}

function credentialsOrNull(): SupabaseCredentials | null {
  try {
    return readCredentials();
  } catch {
    return null;
  }
}

export function publicTeamSnapshotExpiry(
  state: PublicTeamState,
  now: number,
): string | null {
  const current = deadlines.deadlines.find(
    ({ event }) => event === state.event,
  );
  const next = deadlines.deadlines.find(
    ({ event }) => event === state.event + 1,
  );
  const observed = Date.parse(state.dataAvailableAt);
  if (
    !current ||
    !next ||
    Date.parse(current.deadline) !== Date.parse(state.stateAsOf) ||
    observed > now ||
    observed < Date.parse(current.deadline) ||
    now >= Date.parse(next.deadline) ||
    now - observed >= 30 * 86_400_000
  )
    return null;
  return new Date(
    Math.min(Date.parse(next.deadline), observed + 30 * 86_400_000),
  ).toISOString();
}

export class PublicTeamSnapshotStore implements TeamSnapshotStore {
  constructor(
    private readonly credentials: SupabaseCredentials | null = credentialsOrNull(),
    private readonly fetchApi: typeof fetch = fetch,
    private readonly now: () => number = Date.now,
  ) {}

  async read(entryId: number): Promise<PublicTeamState | null> {
    if (!this.credentials) return null;
    try {
      const rows = await this.bounded((fetchApi) =>
        readRows(
          "public_team_snapshots",
          new URLSearchParams({
            select:
              "season,entry_id,event,context_hash,captured_at,expires_at,state",
            season: `eq.${season}`,
            entry_id: `eq.${entryId}`,
            context_hash: `eq.${contextHash}`,
            expires_at: `gt.${new Date(this.now()).toISOString()}`,
            order: "event.desc,captured_at.desc",
            limit: "1",
          }),
          this.credentials!,
          fetchApi,
        ),
      );
      const parsed = rowSchema.safeParse(rows[0]);
      if (!parsed.success) return null;
      const row = parsed.data;
      const validUntil = publicTeamSnapshotExpiry(row.state, this.now());
      if (
        row.entry_id !== entryId ||
        row.state.entryId !== entryId ||
        row.event !== row.state.event ||
        !validUntil ||
        Date.parse(row.expires_at) !== Date.parse(validUntil) ||
        Date.parse(row.captured_at) !== Date.parse(row.state.dataAvailableAt)
      )
        return null;
      return row.state;
    } catch {
      this.report("read_failed");
      return null;
    }
  }

  async write(input: PublicTeamState): Promise<void> {
    if (!this.credentials) return;
    const parsed = publicTeamStateSchema.safeParse(input);
    if (!parsed.success) return;
    const state = parsed.data;
    const expiresAt = publicTeamSnapshotExpiry(state, this.now());
    if (!expiresAt) return;
    try {
      await this.bounded((fetchApi) =>
        upsertRow(
          "public_team_snapshots",
          {
            season,
            entry_id: state.entryId,
            event: state.event,
            context_hash: contextHash,
            captured_at: state.dataAvailableAt,
            expires_at: expiresAt,
            state,
          },
          ["season", "entry_id", "event"],
          this.credentials!,
          fetchApi,
        ),
      );
    } catch {
      this.report("write_failed");
    }
  }

  private async bounded<Value>(
    operation: (fetchApi: typeof fetch) => Promise<Value>,
  ): Promise<Value> {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timedOut = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new Error("Snapshot store timeout"));
      }, 750);
    });
    try {
      return await Promise.race([
        operation((url, init) =>
          this.fetchApi(url, { ...init, signal: controller.signal }),
        ),
        timedOut,
      ]);
    } finally {
      clearTimeout(timer);
    }
  }

  private report(outcome: string): void {
    console.warn(JSON.stringify({ event: "team_snapshot_cache", outcome }));
  }
}
