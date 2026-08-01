import { describe, expect, it, vi } from "vitest";

import {
  clientAddress,
  rateLimitHeaders,
  RateLimiter,
  TEAM_STATE_POLICY,
  type RateLimitPolicy,
} from "../../../../api/_lib/rate-limit";

/**
 * Audit item #72. Both proxies were open, unauthenticated and unbudgeted onto a
 * third party's API.
 *
 * What is asserted here is what the limiter can promise, including where it
 * stops: it is per-instance, so these are the guarantees within one instance.
 * The tests that matter most are the ones about failure -- what happens when
 * the tracking table is full, and what happens when the caller controls the
 * header the key comes from.
 */

const policy: RateLimitPolicy = { perClient: 3, global: 10 };

function limiterAt(clock: { at: number }): RateLimiter {
  return new RateLimiter(policy, () => clock.at);
}

describe("per-client budget", () => {
  it("allows exactly the budget, then refuses", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    for (let index = 0; index < 3; index += 1) {
      expect(limiter.check("a").allowed).toBe(true);
    }
    const refused = limiter.check("a");
    expect(refused.allowed).toBe(false);
    expect(refused.allowed === false && refused.scope).toBe("client");
  });

  it("counts down the remaining budget", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    expect(limiter.check("a")).toMatchObject({ remaining: 2 });
    expect(limiter.check("a")).toMatchObject({ remaining: 1 });
    expect(limiter.check("a")).toMatchObject({ remaining: 0 });
  });

  it("does not charge one client for another's requests", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    for (let index = 0; index < 3; index += 1) limiter.check("a");
    expect(limiter.check("b").allowed).toBe(true);
  });

  it("restores the budget when the window turns over", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    for (let index = 0; index < 3; index += 1) limiter.check("a");
    expect(limiter.check("a").allowed).toBe(false);
    clock.at += 60_000;
    expect(limiter.check("a").allowed).toBe(true);
  });

  it("reports a retry delay of at least one second, never zero", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    for (let index = 0; index < 3; index += 1) limiter.check("a");
    clock.at += 59_999;
    const refused = limiter.check("a");
    expect(refused.allowed).toBe(false);
    expect(refused.allowed === false && refused.retryAfterSeconds).toBe(1);
  });
});

describe("global ceiling", () => {
  it("refuses once the instance total is reached, whatever the key", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    // Ten distinct clients, each well within its own budget of three.
    for (let index = 0; index < 10; index += 1) {
      expect(limiter.check(`client-${index}`).allowed).toBe(true);
    }
    const refused = limiter.check("client-fresh");
    expect(refused.allowed).toBe(false);
    expect(refused.allowed === false && refused.scope).toBe("global");
  });

  it("does not spend the shared budget on a request it refused", () => {
    // Otherwise a single client burning its own budget would also drain the
    // ceiling for everyone else, which turns one bad caller into an outage.
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    for (let index = 0; index < 3; index += 1) limiter.check("noisy");
    for (let index = 0; index < 20; index += 1) limiter.check("noisy");

    let allowed = 0;
    for (let index = 0; index < 10; index += 1) {
      if (limiter.check(`other-${index}`).allowed) allowed += 1;
    }
    expect(allowed).toBe(7);
  });

  it("resets with its own window", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    for (let index = 0; index < 10; index += 1) limiter.check(`c-${index}`);
    expect(limiter.check("c-fresh").allowed).toBe(false);
    clock.at += 60_000;
    expect(limiter.check("c-fresh").allowed).toBe(true);
  });
});

describe("bounded state", () => {
  it("does not grow without limit when every request has a new key", () => {
    // An unbounded map keyed by client address is itself a denial of service:
    // a million addresses would exhaust memory rather than the budget.
    const clock = { at: 1_000_000 };
    const limiter = new RateLimiter(
      { perClient: 3, global: 1_000_000 },
      () => clock.at,
    );
    for (let index = 0; index < 20_000; index += 1) {
      limiter.check(`client-${index}`);
    }
    expect(limiter.trackedClients).toBeLessThanOrEqual(5_000);
  });

  it("sweeps expired windows before declaring the table full", () => {
    const clock = { at: 1_000_000 };
    const limiter = new RateLimiter(
      { perClient: 3, global: 1_000_000 },
      () => clock.at,
    );
    for (let index = 0; index < 5_000; index += 1) {
      limiter.check(`old-${index}`);
    }
    clock.at += 60_001;
    limiter.check("new-arrival");
    expect(limiter.trackedClients).toBeLessThan(5_000);
  });

  it("keeps serving under a key flood rather than locking everyone out", () => {
    const clock = { at: 1_000_000 };
    const limiter = new RateLimiter(
      { perClient: 3, global: 1_000_000 },
      () => clock.at,
    );
    for (let index = 0; index < 6_000; index += 1) {
      limiter.check(`flood-${index}`);
    }
    const decision = limiter.check("someone-real");
    expect(decision.allowed).toBe(true);
    // The degradation is named rather than silent: the global ceiling is now
    // the only limit in force, and the log says so.
    expect(decision).toHaveProperty("degraded", "client_table_full");
  });
});

describe("client key", () => {
  it("uses the platform header a caller cannot set", () => {
    expect(
      clientAddress({
        "x-vercel-forwarded-for": "203.0.113.7",
        "x-forwarded-for": "1.1.1.1",
        "x-real-ip": "2.2.2.2",
      }),
    ).toBe("203.0.113.7");
  });

  it("ignores x-forwarded-for entirely, which the caller controls", () => {
    // Keying on a caller-supplied header would let one client present as a
    // million and never meet the per-client limit at all.
    expect(clientAddress({ "x-forwarded-for": "1.1.1.1" })).toBe(
      "unattributed",
    );
  });

  it("falls back to x-real-ip", () => {
    expect(clientAddress({ "x-real-ip": "198.51.100.4" })).toBe("198.51.100.4");
  });

  it("takes the first address when the header carries a chain", () => {
    expect(
      clientAddress({ "x-vercel-forwarded-for": "203.0.113.7, 10.0.0.1" }),
    ).toBe("203.0.113.7");
  });

  it("shares one key off-platform, so the limit degrades to global not absent", () => {
    expect(clientAddress({})).toBe("unattributed");
    expect(clientAddress({ "x-real-ip": "  " })).toBe("unattributed");
    expect(clientAddress({ "x-real-ip": [] })).toBe("unattributed");
  });

  it("reads the first entry of a repeated header", () => {
    expect(clientAddress({ "x-real-ip": ["198.51.100.4", "1.1.1.1"] })).toBe(
      "198.51.100.4",
    );
  });
});

describe("response headers", () => {
  it("advertises the limit and what is left", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    const headers = rateLimitHeaders(policy, limiter.check("a"));
    expect(headers).toEqual({
      "RateLimit-Limit": "3",
      "RateLimit-Remaining": "2",
    });
  });

  it("sends Retry-After on a refusal so a client knows when to return", () => {
    const clock = { at: 1_000_000 };
    const limiter = limiterAt(clock);
    for (let index = 0; index < 3; index += 1) limiter.check("a");
    const headers = rateLimitHeaders(policy, limiter.check("a"));
    expect(headers["Retry-After"]).toBe("60");
    expect(headers["RateLimit-Remaining"]).toBe("0");
  });
});

describe("shipped policy", () => {
  it("gives the team endpoint a smaller budget than the raw proxy", () => {
    // One /api/team call fans out to three upstream requests, one of which is
    // the 1.3 MB bootstrap document.
    expect(TEAM_STATE_POLICY.perClient).toBeLessThan(60);
    expect(TEAM_STATE_POLICY.global).toBeLessThan(600);
  });

  it("leaves a real page comfortably inside the budget", () => {
    // A first load fetches team state once and may retry; twenty a minute is
    // far more than any interface here asks for.
    const clock = { at: 1_000_000 };
    const limiter = new RateLimiter(TEAM_STATE_POLICY, () => clock.at);
    for (let index = 0; index < 10; index += 1) {
      expect(limiter.check("real-visitor").allowed).toBe(true);
    }
  });
});

describe("default clock", () => {
  it("uses wall time when none is injected", () => {
    const spy = vi.spyOn(Date, "now");
    new RateLimiter(policy).check("a");
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});
