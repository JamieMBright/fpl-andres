import {
  teamStateOverridesSchema,
  type TeamStateOverrides,
} from "@fpl-andres/contracts";
import { z } from "zod";

const STORAGE_PREFIX = "fpl-andres:team-state-overrides:v1";
const publicIdSchema = z.int().min(1).max(4_294_967_295);
const deadlineSchema = z.iso.datetime();

export function teamStateOverridesStorageKey(
  entryId: number,
  deadline: string,
): string {
  const parsedEntryId = publicIdSchema.safeParse(entryId);
  if (!parsedEntryId.success) {
    throw new TypeError("entry ID is outside the supported range");
  }
  const parsedDeadline = deadlineSchema.safeParse(deadline);
  if (!parsedDeadline.success) {
    throw new TypeError("public deadline must be an ISO UTC timestamp");
  }
  return `${STORAGE_PREFIX}:${parsedEntryId.data}:${parsedDeadline.data}`;
}

/**
 * A later write silently discarded an earlier correction.
 *
 * This filed this against a Python module. There is no write path
 * there -- `team_state.py` only resolves -- but the concern is real and lives
 * here instead: two tabs open on the same manager, both editing. The second
 * `setItem` wins, the first tab still shows what it saved, and nothing tells
 * anyone the two disagree. The loss is invisible precisely because both writes
 * succeed.
 *
 * The precondition is what the writer believed it was editing. Comparing
 * timestamps instead would not work: the second tab's `updatedAt` is genuinely
 * newer, so "newer wins" accepts exactly the write that loses the correction.
 */
export class TeamStateOverridesConflictError extends Error {
  override name = "TeamStateOverridesConflictError";
  constructor(readonly stored: TeamStateOverrides | null) {
    super(
      "These corrections were changed in another tab. Reload them before saving.",
    );
  }
}

export interface SavePrecondition {
  /**
   * The `updatedAt` of the record this write is based on, or `null` when the
   * writer believed nothing was stored.
   */
  expectedUpdatedAt: string | null;
}

export function saveTeamStateOverrides(
  storage: Storage,
  entryId: number,
  input: unknown,
  precondition?: SavePrecondition,
): TeamStateOverrides {
  const overrides = teamStateOverridesSchema.parse(input);
  const key = teamStateOverridesStorageKey(entryId, overrides.basedOnStateAsOf);
  if (precondition !== undefined) {
    // Read immediately before the write. localStorage is synchronous and
    // single-threaded within a tab, so nothing can interleave between these two
    // statements; the race being closed is between tabs, not within one.
    const stored = readStored(storage, key, overrides.basedOnStateAsOf);
    const storedUpdatedAt = stored?.updatedAt ?? null;
    if (storedUpdatedAt !== precondition.expectedUpdatedAt) {
      throw new TeamStateOverridesConflictError(stored);
    }
  }
  pruneOtherOverridesForEntry(storage, entryId, key);
  storage.setItem(key, JSON.stringify(overrides));
  return overrides;
}

function pruneOtherOverridesForEntry(
  storage: Storage,
  entryId: number,
  keepKey: string,
): void {
  const parsedEntryId = publicIdSchema.safeParse(entryId);
  if (!parsedEntryId.success) return;
  const prefix = `${STORAGE_PREFIX}:${parsedEntryId.data}:`;
  const staleKeys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const candidate = storage.key(index);
    if (candidate === null) continue;
    if (candidate === keepKey) continue;
    if (candidate.startsWith(prefix)) staleKeys.push(candidate);
  }
  for (const stale of staleKeys) storage.removeItem(stale);
}

export function loadTeamStateOverrides(
  storage: Storage,
  entryId: number,
  deadline: string,
): TeamStateOverrides | null {
  return readStored(
    storage,
    teamStateOverridesStorageKey(entryId, deadline),
    deadline,
  );
}

/**
 * Read one record, discarding anything that no longer parses or no longer
 * belongs to this deadline. A corrupt or stale record is removed rather than
 * left to fail the same way on every load.
 */
function readStored(
  storage: Storage,
  key: string,
  deadline: string,
): TeamStateOverrides | null {
  const serialized = storage.getItem(key);
  if (serialized === null) {
    return null;
  }

  try {
    const parsed = teamStateOverridesSchema.safeParse(JSON.parse(serialized));
    if (!parsed.success || parsed.data.basedOnStateAsOf !== deadline) {
      storage.removeItem(key);
      return null;
    }
    return parsed.data;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

export function removeTeamStateOverrides(
  storage: Storage,
  entryId: number,
  deadline: string,
): void {
  storage.removeItem(teamStateOverridesStorageKey(entryId, deadline));
}
