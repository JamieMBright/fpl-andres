/**
 * Coalescing and short-lived caching for the upstream sources.
 *
 * Audit item #87. Every call to `/api/team/:id` fetched the bootstrap document
 * -- 1.3 MB, identical for every caller, and unchanged for minutes at a time.
 * Ten people looking up their teams in the same second pulled it ten times.
 * The cost lands on FPL, under this project's user agent, which is the same
 * concern that produced the request budget in `rate-limit.ts`.
 *
 * Two mechanisms, because they answer different questions.
 *
 * Coalescing answers "is this same request already in flight?" It is safe for
 * every source, including per-manager ones: two concurrent requests for the
 * same manager's picks would receive the same bytes anyway, so serving both
 * from one fetch changes nothing a caller could observe.
 *
 * Caching answers "did we fetch this recently enough?" It is safe only where
 * the answer does not depend on who is asking. Bootstrap qualifies; an entry
 * or a picks response does not, and gets a TTL of zero -- coalesced but never
 * held. That mirrors `cachePolicyFor` in `fpl-proxy.ts`, and for the same
 * reason: the default is private and a new source has to be named to become
 * shared.
 *
 * A rejected promise is never cached and never left in the in-flight table. A
 * cache that remembers failures turns one bad minute into several.
 */

const MAX_ENTRIES = 32;

export interface CacheClock {
  (): number;
}

interface Entry<T> {
  value: T;
  expiresAt: number;
}

export interface Resolved<T> {
  value: T;
  /** True when nothing was fetched: served from the cache or from a shared flight. */
  reused: boolean;
}

export class SourceCache<T> {
  readonly #fresh = new Map<string, Entry<T>>();
  readonly #inFlight = new Map<string, Promise<T>>();

  constructor(private readonly now: CacheClock = Date.now) {}

  /**
   * @param ttlMs 0 means coalesce only: share an in-flight fetch, keep nothing.
   * @param isCacheable Decides whether a *resolved* value may be held. A failed
   *   upstream read resolves with a failure outcome rather than rejecting, so
   *   rejection alone is not enough to keep failures out of the cache. Without
   *   this, one bad moment for bootstrap becomes a minute of degraded responses
   *   for everyone -- the cache would be serving the outage.
   */
  async resolve(
    key: string,
    ttlMs: number,
    load: () => Promise<T>,
    isCacheable: (value: T) => boolean = () => true,
  ): Promise<Resolved<T>> {
    const at = this.now();
    if (ttlMs > 0) {
      const cached = this.#fresh.get(key);
      if (cached !== undefined && at < cached.expiresAt) {
        return { value: cached.value, reused: true };
      }
      if (cached !== undefined) this.#fresh.delete(key);
    }

    const existing = this.#inFlight.get(key);
    if (existing !== undefined) return { value: await existing, reused: true };

    const pending = load();
    this.#inFlight.set(key, pending);
    // Not `.finally()`: it re-throws, which produces an unhandled rejection for
    // every caller that shared the promise but did not await this branch.
    pending.then(
      (value) => {
        this.#inFlight.delete(key);
        if (ttlMs > 0 && isCacheable(value)) {
          this.#store(key, value, this.now() + ttlMs);
        }
      },
      () => {
        this.#inFlight.delete(key);
      },
    );
    return { value: await pending, reused: false };
  }

  clear(): void {
    this.#fresh.clear();
    this.#inFlight.clear();
  }

  get size(): number {
    return this.#fresh.size;
  }

  #store(key: string, value: T, expiresAt: number): void {
    if (this.#fresh.size >= MAX_ENTRIES && !this.#fresh.has(key)) {
      const at = this.now();
      for (const [existing, entry] of this.#fresh) {
        if (at >= entry.expiresAt) this.#fresh.delete(existing);
      }
      if (this.#fresh.size >= MAX_ENTRIES) {
        // Oldest insertion first: Map preserves it, and a bounded cache that
        // refuses to evict is a memory leak with extra steps.
        const oldest = this.#fresh.keys().next();
        if (!oldest.done) this.#fresh.delete(oldest.value);
      }
    }
    this.#fresh.set(key, { value, expiresAt });
  }
}

/**
 * How long a source may be reused, in milliseconds.
 *
 * Bootstrap matches the 60 seconds `fpl-proxy.ts` already tells a CDN it may
 * hold the same document for; using a different number here would mean two
 * layers disagreeing about how stale the same bytes are allowed to be.
 */
export function sourceTtlMs(source: string): number {
  return source === "bootstrap" ? 60_000 : 0;
}
