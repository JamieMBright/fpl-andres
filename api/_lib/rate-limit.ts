/**
 * A request budget for the two unauthenticated proxies.
 *
 * `/api/fpl/*` and `/api/team/*` are open proxies onto a third
 * party's API. Anyone could point a loop at them, and the cost lands twice:
 * on this deployment's function-seconds, and on the Premier League's servers
 * under this project's user agent. The second is the one that gets a project
 * blocked.
 *
 * Two limits, because they fail differently.
 *
 * A per-client limit stops the ordinary case: a script left in a loop, a page
 * that re-renders in a cycle, one person hammering. It is keyed by the client
 * address the platform reports and it can be evaded by anyone with more than
 * one address, which is fine -- it is not there for them.
 *
 * A global ceiling stops the case the per-client limit cannot: many keys, each
 * under its own budget, adding up to a flood upstream. It cannot be evaded by
 * rotating addresses because it does not look at them. It is deliberately
 * generous, since it also throttles legitimate traffic once tripped, and it is
 * the last thing standing between a botnet and the FPL API.
 *
 * In-memory and per-instance, which bounds what it can promise: with several
 * warm instances a client gets the per-client budget several times over. That
 * is a real limitation and it is written down rather than papered over. A
 * global limit needs shared state -- Vercel's WAF, or a Redis the owner
 * chooses to run -- and that is an infrastructure decision, not a code one.
 * The README's operations section records what this does and does not cover.
 *
 * The state is bounded. An unbounded map keyed by client address is itself a
 * denial of service: an attacker sending one request from each of a million
 * addresses would exhaust the function's memory rather than its budget.
 */

const WINDOW_MS = 60_000;
const MAX_TRACKED_CLIENTS = 5_000;

export interface RateLimitPolicy {
  /** Requests one client may make within a window. */
  perClient: number;
  /** Requests this instance will make within a window, across all clients. */
  global: number;
}

export const FPL_PROXY_POLICY: RateLimitPolicy = {
  perClient: 60,
  global: 600,
};

/**
 * Lower, because one call fans out to three upstream requests including the
 * 1.3 MB bootstrap document.
 */
export const TEAM_STATE_POLICY: RateLimitPolicy = {
  perClient: 20,
  global: 200,
};

/** Contact sends mail, so its abuse budget is deliberately much smaller. */
export const CONTACT_POLICY: RateLimitPolicy = {
  perClient: 3,
  global: 30,
};

export type RateLimitDecision =
  | { allowed: true; remaining: number }
  | { allowed: true; remaining: number; degraded: "client_table_full" }
  | { allowed: false; retryAfterSeconds: number; scope: "client" | "global" };

interface Window {
  count: number;
  resetAt: number;
}

export class RateLimiter {
  readonly #clients = new Map<string, Window>();
  #global: Window = { count: 0, resetAt: 0 };

  constructor(
    private readonly policy: RateLimitPolicy,
    private readonly now: () => number = Date.now,
  ) {}

  check(clientKey: string): RateLimitDecision {
    const at = this.now();

    // The global window is checked first and consumed last: a request refused
    // for exceeding its own budget must not also spend from the shared one.
    if (at >= this.#global.resetAt) {
      this.#global = { count: 0, resetAt: at + WINDOW_MS };
    }
    if (this.#global.count >= this.policy.global) {
      return {
        allowed: false,
        retryAfterSeconds: secondsUntil(this.#global.resetAt, at),
        scope: "global",
      };
    }

    let window = this.#clients.get(clientKey);
    if (window === undefined || at >= window.resetAt) {
      if (window === undefined && this.#clients.size >= MAX_TRACKED_CLIENTS) {
        this.#sweep(at);
      }
      if (window === undefined && this.#clients.size >= MAX_TRACKED_CLIENTS) {
        // The table is full of live windows. Allowing the request keeps the
        // global ceiling as the only limit, which is the one that matters at
        // this scale anyway; refusing would turn a memory bound into an
        // outage for whoever arrived last.
        this.#global.count += 1;
        return {
          allowed: true,
          remaining: this.policy.global - this.#global.count,
          degraded: "client_table_full",
        };
      }
      window = { count: 0, resetAt: at + WINDOW_MS };
      this.#clients.set(clientKey, window);
    }

    if (window.count >= this.policy.perClient) {
      return {
        allowed: false,
        retryAfterSeconds: secondsUntil(window.resetAt, at),
        scope: "client",
      };
    }

    window.count += 1;
    this.#global.count += 1;
    return { allowed: true, remaining: this.policy.perClient - window.count };
  }

  /** Test seam: a limiter that outlives a test would leak its counts into the next. */
  reset(): void {
    this.#clients.clear();
    this.#global = { count: 0, resetAt: 0 };
  }

  get trackedClients(): number {
    return this.#clients.size;
  }

  #sweep(at: number): void {
    for (const [key, window] of this.#clients) {
      if (at >= window.resetAt) this.#clients.delete(key);
    }
  }
}

function secondsUntil(resetAt: number, at: number): number {
  return Math.max(1, Math.ceil((resetAt - at) / 1000));
}

export interface ClientAddressHeaders {
  [name: string]: string | string[] | undefined;
}

/**
 * The client address, from a header the client cannot set.
 *
 * `x-forwarded-for` arrives from the caller and is appended to, so its leftmost
 * entry is whatever the caller wrote there: keying on it would let one client
 * present as a million. Vercel sets `x-vercel-forwarded-for` and `x-real-ip`
 * itself and overwrites any inbound copy, so those are the trustworthy ones.
 *
 * When neither is present -- running outside the platform -- every caller
 * shares one key. That makes the per-client limit behave as a second global
 * limit rather than as no limit, which is the safe direction to fail.
 */
export function clientAddress(
  headers: ClientAddressHeaders | undefined,
): string {
  return (
    firstValue(headers?.["x-vercel-forwarded-for"]) ??
    firstValue(headers?.["x-real-ip"]) ??
    "unattributed"
  );
}

function firstValue(raw: string | string[] | undefined): string | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== "string") return null;
  const address = value.split(",")[0]?.trim() ?? "";
  return address === "" ? null : address;
}

export function rateLimitHeaders(
  policy: RateLimitPolicy,
  decision: RateLimitDecision,
): Record<string, string> {
  if (decision.allowed) {
    return {
      "RateLimit-Limit": String(policy.perClient),
      "RateLimit-Remaining": String(Math.max(0, decision.remaining)),
    };
  }
  return {
    "RateLimit-Limit": String(policy.perClient),
    "RateLimit-Remaining": "0",
    "Retry-After": String(decision.retryAfterSeconds),
  };
}
