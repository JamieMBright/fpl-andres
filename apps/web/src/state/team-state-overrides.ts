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

export function saveTeamStateOverrides(
  storage: Storage,
  entryId: number,
  input: unknown,
): TeamStateOverrides {
  const overrides = teamStateOverridesSchema.parse(input);
  const key = teamStateOverridesStorageKey(entryId, overrides.basedOnStateAsOf);
  storage.setItem(key, JSON.stringify(overrides));
  return overrides;
}

export function loadTeamStateOverrides(
  storage: Storage,
  entryId: number,
  deadline: string,
): TeamStateOverrides | null {
  const key = teamStateOverridesStorageKey(entryId, deadline);
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
