import { z } from "zod";

/**
 * Which player-pool columns are shown, and in what order.
 *
 * The table has grown from six columns to a dozen and more are still being
 * asked for. A fixed layout forces every reader to scroll past columns they
 * never look at to reach the one they do; this lets each reader keep only
 * what they use, in the order they read it.
 *
 * Held in `localStorage` because it is a display preference, not a claim
 * about a squad — there is nothing here worth a server round trip or worth
 * protecting the way a declared transfer is.
 */

const STORAGE_KEY = "fpl-andres:pool-columns";

const storedSchema = z.array(z.string().min(1)).max(64);

/**
 * Reconciles a stored order against the columns that actually exist today.
 *
 * A column can be renamed or removed between releases; a stored order should
 * not resurrect a key that no longer means anything, and it should not hide a
 * new column just because it did not exist when the order was saved.
 */
export function readColumnOrder<Key extends string>(
  storage: Storage,
  defaultOrder: readonly Key[],
): Key[] {
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) return [...defaultOrder];
  let parsed: string[];
  try {
    const result = storedSchema.safeParse(JSON.parse(raw));
    if (!result.success) {
      storage.removeItem(STORAGE_KEY);
      return [...defaultOrder];
    }
    parsed = result.data;
  } catch {
    storage.removeItem(STORAGE_KEY);
    return [...defaultOrder];
  }
  const known = new Set<string>(defaultOrder);
  const kept = parsed.filter((key): key is Key => known.has(key));
  const seen = new Set(kept);
  const added = defaultOrder.filter((key) => !seen.has(key));
  return [...kept, ...added];
}

export function saveColumnOrder(
  storage: Storage,
  order: readonly string[],
): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(order));
}

const VISIBLE_STORAGE_KEY = "fpl-andres:pool-columns-hidden";

const hiddenSchema = z.array(z.string().min(1)).max(64);

export function readHiddenColumns(
  storage: Storage,
  defaultHidden: readonly string[] = [],
): Set<string> {
  const raw = storage.getItem(VISIBLE_STORAGE_KEY);
  if (!raw) return new Set(defaultHidden);
  try {
    const result = hiddenSchema.safeParse(JSON.parse(raw));
    if (!result.success) {
      storage.removeItem(VISIBLE_STORAGE_KEY);
      return new Set(defaultHidden);
    }
    return new Set(result.data);
  } catch {
    storage.removeItem(VISIBLE_STORAGE_KEY);
    return new Set(defaultHidden);
  }
}

export function saveHiddenColumns(
  storage: Storage,
  hidden: ReadonlySet<string>,
): void {
  storage.setItem(VISIBLE_STORAGE_KEY, JSON.stringify([...hidden]));
}

/**
 * One row of already-formatted cell text per visible column, turned into an
 * RFC 4180 CSV. Values are formatted upstream so the file reads the same
 * numbers the table shows — a dash for a missing record, not an empty cell
 * that looks like a data-entry mistake.
 */
export function toCsv(header: string[], rows: string[][]): string {
  const escape = (value: string): string =>
    /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
  return [header, ...rows].map((row) => row.map(escape).join(",")).join("\r\n");
}
