/**
 * Net movement in the FPL500 cohort, read from the squads themselves.
 *
 * FPL's own transfer counters are per manager and private; what is public is
 * two consecutive ownership snapshots. The difference between them across a
 * gameweek's captured holdings IS the cohort's net movement on that player —
 * not individual transfers, but the same signal read a different way: how
 * many more (or fewer) of the five hundred hold him now than held him before.
 *
 * This is deliberately the cohort's own flow, not the game's: it is read
 * entirely from `holdings`, which is anonymised ownership, never from a
 * manager's private transfer history.
 */

export interface TransferFlowInputSample {
  counted: number;
}

export interface TransferFlowInputHolding {
  elementId: number;
  ownedShare: number;
  name?: string;
  club?: string;
  position?: "GKP" | "DEF" | "MID" | "FWD";
}

export interface TransferFlowSeriesLike {
  events: readonly number[];
  samples: Record<string, TransferFlowInputSample | undefined>;
  holdings?: Record<string, readonly TransferFlowInputHolding[] | undefined>;
}

export interface TransferFlowPlayer {
  elementId: number;
  name: string;
  club: string;
  position: "GKP" | "DEF" | "MID" | "FWD" | "UNK";
  /** Summed increase in owned count across the window. */
  transfersIn: number;
  /** Summed decrease in owned count across the window, as a positive number. */
  transfersOut: number;
  /** `transfersIn - transfersOut`. Positive: the cohort is buying him. */
  net: number;
}

function key(event: number): string {
  return String(event).padStart(2, "0");
}

function ownedCount(
  holding: TransferFlowInputHolding | undefined,
  counted: number,
): number {
  return holding ? Math.round(holding.ownedShare * counted) : 0;
}

/**
 * How many gameweek-to-gameweek transitions the captured events actually
 * have. One captured gameweek has none: there is nothing yet to compare it
 * to.
 */
export function transferFlowTransitionCount(
  series: TransferFlowSeriesLike,
): number {
  return Math.max(0, series.events.length - 1);
}

/**
 * Net movement per player over the last `window` transitions.
 *
 * `window` is clamped to what is actually captured, so asking for five weeks
 * with two captured gives the one transition that exists rather than nothing.
 */
export function transferFlow(
  series: TransferFlowSeriesLike,
  window: number,
): TransferFlowPlayer[] {
  const events = [...series.events].sort((left, right) => left - right);
  const transitions = Math.max(0, events.length - 1);
  const used = Math.max(0, Math.min(window, transitions));
  if (used === 0) return [];

  const startIndex = events.length - 1 - used;
  const rows = new Map<number, TransferFlowPlayer>();

  for (let index = startIndex; index < events.length - 1; index += 1) {
    const beforeEvent = events[index];
    const afterEvent = events[index + 1];
    if (beforeEvent === undefined || afterEvent === undefined) continue;
    const beforeHoldings = series.holdings?.[key(beforeEvent)] ?? [];
    const afterHoldings = series.holdings?.[key(afterEvent)] ?? [];
    const beforeCounted = series.samples[key(beforeEvent)]?.counted ?? 0;
    const afterCounted = series.samples[key(afterEvent)]?.counted ?? 0;
    const beforeById = new Map(
      beforeHoldings.map((holding) => [holding.elementId, holding]),
    );
    const afterById = new Map(
      afterHoldings.map((holding) => [holding.elementId, holding]),
    );
    const elementIds = new Set([...beforeById.keys(), ...afterById.keys()]);

    for (const elementId of elementIds) {
      const before = ownedCount(beforeById.get(elementId), beforeCounted);
      const after = ownedCount(afterById.get(elementId), afterCounted);
      const delta = after - before;
      if (delta === 0) continue;
      const source = afterById.get(elementId) ?? beforeById.get(elementId);
      const existing = rows.get(elementId) ?? {
        elementId,
        name: source?.name ?? `Element ${String(elementId)}`,
        club: source?.club ?? "",
        position: source?.position ?? "UNK",
        transfersIn: 0,
        transfersOut: 0,
        net: 0,
      };
      const next: TransferFlowPlayer = {
        ...existing,
        transfersIn: existing.transfersIn + Math.max(0, delta),
        transfersOut: existing.transfersOut + Math.max(0, -delta),
      };
      rows.set(elementId, {
        ...next,
        net: next.transfersIn - next.transfersOut,
      });
    }
  }

  return [...rows.values()].sort(
    (left, right) =>
      right.net - left.net || left.name.localeCompare(right.name),
  );
}
