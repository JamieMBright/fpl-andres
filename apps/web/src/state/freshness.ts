/**
 * How current the data on screen actually is.
 *
 * The proxy can now answer a failed upstream with the last copy of a public
 * document it holds, and the browser can fall back to the last pool it
 * rendered. Both are better than an empty page. Both are also indistinguishable
 * from live data once they are drawn, which is the failure mode worth being
 * careful about: a price or an injury flag from forty minutes ago presented as
 * current is worse than no page at all, because a manager acts on it.
 *
 * So every pool carries this, and anything showing a pool that is not live says
 * so in words, with a time attached.
 */

export interface Freshness {
  /** When these bytes left FPL, as far as anything here can tell. */
  capturedAt: number;
  /** True when this is not what FPL is saying now. */
  stale: boolean;
  /** Seconds since capture, when the source said. Null when it did not. */
  ageSeconds: number | null;
}

export const LIVE: Freshness = {
  capturedAt: 0,
  stale: false,
  ageSeconds: null,
};

/**
 * Read the staleness the proxy declared.
 *
 * `X-FPL-Stale-Age` and `X-FPL-Captured-At` are set by `api/_lib/fpl-proxy.ts`
 * when it serves a retained copy. Their absence means the response is live --
 * the header is only ever added, never omitted on a stale answer, so absence
 * is not an ambiguous case.
 */
export function freshnessOf(response: Response, now = Date.now()): Freshness {
  if (response.headers.get("X-FPL-Stale") !== "1") {
    return { capturedAt: now, stale: false, ageSeconds: null };
  }
  const rawAge = response.headers.get("X-FPL-Stale-Age") ?? "";
  const ageSeconds = /^\d+$/.test(rawAge) ? Number(rawAge) : null;
  const capturedAt = Date.parse(
    response.headers.get("X-FPL-Captured-At") ?? "",
  );
  return {
    capturedAt: Number.isFinite(capturedAt)
      ? capturedAt
      : now - (ageSeconds ?? 0) * 1_000,
    stale: true,
    ageSeconds,
  };
}

/** Combine the freshness of the several documents one view is built from. */
export function leastFresh(parts: Freshness[]): Freshness {
  return parts.reduce((worst, part) => {
    if (!part.stale) return worst;
    if (!worst.stale) return part;
    return part.capturedAt < worst.capturedAt ? part : worst;
  }, LIVE);
}

/**
 * The last value that was successfully built, kept for the length of the tab.
 *
 * Module scope rather than component state, so navigating away from the player
 * list and back does not throw away a working pool and re-run a fetch that is
 * currently failing. Not persisted: a stale pool is a stopgap for an outage
 * happening now, and one restored from a previous visit could be days old.
 */
export class LastGood<T> {
  #held: { value: T; at: number } | null = null;

  remember(value: T, at = Date.now()): void {
    this.#held = { value, at };
  }

  recall(): { value: T; freshness: Freshness } | null {
    if (this.#held === null) return null;
    const ageMs = Math.max(0, Date.now() - this.#held.at);
    return {
      value: this.#held.value,
      freshness: {
        capturedAt: this.#held.at,
        stale: true,
        ageSeconds: Math.round(ageMs / 1_000),
      },
    };
  }

  forget(): void {
    this.#held = null;
  }
}

/**
 * One sentence a reader can act on, rather than a timestamp they have to
 * interpret. Deliberately blunt about what it is: not current.
 */
export function describeFreshness(freshness: Freshness): string {
  if (!freshness.stale) return "";
  const seconds = freshness.ageSeconds;
  if (seconds === null) {
    return "This is the last player list I was able to read, not the current one. Prices and injury flags may have moved since.";
  }
  const minutes = Math.round(seconds / 60);
  const when =
    minutes < 1
      ? "less than a minute ago"
      : minutes === 1
        ? "a minute ago"
        : minutes < 60
          ? `${String(minutes)} minutes ago`
          : `${String(Math.round(minutes / 60))} hours ago`;
  return `FPL is not answering. This is the player list as it stood ${when}. Prices and injury flags may have moved since.`;
}
