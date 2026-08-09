import { entryHistorySchema } from "./manager-profile";

/**
 * The manager's own record, kept on the manager's own device.
 *
 * FPL turns this deployment away from time to time, and a cold serverless
 * instance has no last-known-good copy to fall back on. The alternative
 * considered was serving the swept cohort: measured, that is 2,207 managers
 * out of the 2,178,517 the sweep actually read, every one of them filtered on
 * a top-10,000 finish, and it does not contain the team that failed. Sweeping
 * the whole register instead would be roughly three gigabytes and six days of
 * requests aimed at the service that is already refusing us.
 *
 * So this holds nothing but what the reader has already been shown, where only
 * they can see it. Past seasons are settled and never change again, which is
 * why a copy is old rather than wrong; the live season is dropped on the way
 * in, because that one does change.
 */
const STORAGE_PREFIX = "fpl-andres:manager-history:v1";

export function managerHistoryStorageKey(entryId: number): string {
  return `${STORAGE_PREFIX}:${String(entryId)}`;
}

/** Only what reads back through the schema is kept, so a copy is never a guess. */
export function saveManagerHistory(
  storage: Storage,
  entryId: number,
  payload: unknown,
): void {
  const parsed = entryHistorySchema.safeParse(payload);
  if (!parsed.success) return;

  // One manager at a time: a shared browser should not accumulate strangers.
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (key?.startsWith(STORAGE_PREFIX)) storage.removeItem(key);
  }
  storage.setItem(
    managerHistoryStorageKey(entryId),
    JSON.stringify({ past: parsed.data.past }),
  );
}

export function loadManagerHistory(
  storage: Storage,
  entryId: number,
): { past: unknown[] } | null {
  const key = managerHistoryStorageKey(entryId);
  const serialized = storage.getItem(key);
  if (serialized === null) return null;

  try {
    const parsed = entryHistorySchema.safeParse(JSON.parse(serialized));
    if (!parsed.success) {
      storage.removeItem(key);
      return null;
    }
    return { past: parsed.data.past };
  } catch {
    storage.removeItem(key);
    return null;
  }
}
