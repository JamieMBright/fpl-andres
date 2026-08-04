import { describe, expect, it } from "vitest";

import {
  classify,
  overallVerdict,
  probe,
  PROBE_TARGETS,
  probeAll,
  type ProbeTarget,
} from "./diagnostics";

const bootstrap = PROBE_TARGETS.find((target) => target.id === "bootstrap");
if (!bootstrap) throw new Error("the bootstrap probe target went missing");

const health = PROBE_TARGETS.find((target) => target.id === "health");
if (!health) throw new Error("the health probe target went missing");

function headers(values: Record<string, string>): Headers {
  return new Headers(values);
}

describe("classify", () => {
  it("names a bare 500 as a crashed function rather than an upstream fault", () => {
    const verdict = classify(
      bootstrap,
      500,
      headers({ "content-type": "text/html" }),
      "<!doctype html>",
    );

    expect(verdict.verdict).toBe("function_crashed");
    expect(verdict.summary).toContain("build or module-load");
  });

  it("reads Vercel's own error header even when the status looks ordinary", () => {
    const verdict = classify(
      bootstrap,
      502,
      headers({
        "content-type": "text/plain",
        "x-vercel-error": "FUNCTION_INVOCATION_FAILED",
      }),
      "",
    );

    expect(verdict.verdict).toBe("function_crashed");
    expect(verdict.vercelError).toBe("FUNCTION_INVOCATION_FAILED");
  });

  /**
   * The failure that started this: a function that is declared but not routed
   * is answered by the single-page rewrite, so it looks like a working site.
   */
  it("treats the app shell as an unrouted function", () => {
    const verdict = classify(
      bootstrap,
      200,
      headers({ "content-type": "text/html; charset=utf-8" }),
      "<!doctype html><html>",
    );

    expect(verdict.verdict).toBe("not_routed");
  });

  it("distinguishes an FPL block from an FPL timeout", () => {
    const blocked = classify(
      bootstrap,
      502,
      headers({ "content-type": "application/json" }),
      '{"error":"FPL returned an unexpected response format.","reason":"unexpected_format"}',
    );
    const unreachable = classify(
      bootstrap,
      502,
      headers({ "content-type": "application/json" }),
      '{"error":"FPL could not be reached within the request budget.","reason":"unreachable"}',
    );

    expect(blocked.verdict).toBe("upstream_blocked");
    expect(blocked.summary).toContain("bot-protection");
    expect(unreachable.verdict).toBe("upstream_unreachable");
    expect(unreachable.summary).toContain("upstream_exhausted");
  });

  it("surfaces the correlation id so a log search has something to pivot on", () => {
    const verdict = classify(
      bootstrap,
      502,
      headers({
        "content-type": "application/json",
        "x-fpl-andres-request-id": "abc-123",
      }),
      '{"reason":"unreachable"}',
    );

    expect(verdict.requestId).toBe("abc-123");
  });

  it("reports a 200 carrying the wrong shape rather than calling it healthy", () => {
    const verdict = classify(
      bootstrap,
      200,
      headers({ "content-type": "application/json" }),
      '{"something":"else"}',
    );

    expect(verdict.verdict).toBe("unexpected");
  });

  it("passes a healthy response", () => {
    const verdict = classify(
      bootstrap,
      200,
      headers({ "content-type": "application/json" }),
      '{"elements":[{"id":1}]}',
    );

    expect(verdict.verdict).toBe("ok");
  });

  it("names rate limiting as itself, so it is not mistaken for an outage", () => {
    const verdict = classify(
      bootstrap,
      429,
      headers({ "content-type": "application/json" }),
      '{"reason":"rate_limited"}',
    );

    expect(verdict.verdict).toBe("rate_limited");
  });
});

describe("probe", () => {
  it("reports rather than throws when the request cannot be made", async () => {
    const result = await probe(bootstrap, () =>
      Promise.reject(new Error("network down")),
    );

    expect(result.verdict).toBe("upstream_unreachable");
    expect(result.summary).toContain("network down");
  });

  it("records the status and elapsed time of a successful probe", async () => {
    let clock = 0;
    const result = await probe(
      health,
      () =>
        Promise.resolve(
          new Response("{}", {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
      () => (clock += 25),
    );

    expect(result.status).toBe(200);
    expect(result.durationMs).toBe(25);
  });
});

describe("probeAll", () => {
  it("probes every target in order, so a shared rate limit is not self-inflicted", async () => {
    const seen: string[] = [];
    const results = await probeAll(
      (input) => {
        seen.push(String(input));
        return Promise.resolve(
          new Response('{"elements":[1]}', {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      },
      PROBE_TARGETS.slice(0, 2) as ProbeTarget[],
    );

    expect(seen).toEqual(["/api/health", "/api/fpl/bootstrap-static"]);
    expect(results).toHaveLength(2);
  });
});

describe("overallVerdict", () => {
  it("leads with the failing cause when something is broken", async () => {
    const results = await probeAll(
      () =>
        Promise.resolve(
          new Response("<!doctype html>", {
            status: 200,
            headers: { "content-type": "text/html" },
          }),
        ),
      [bootstrap],
    );

    expect(overallVerdict(results)).toContain("app shell");
  });

  it("says so plainly when everything passes", async () => {
    const results = await probeAll(
      () =>
        Promise.resolve(
          new Response('{"elements":[1]}', {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
      [bootstrap],
    );

    expect(overallVerdict(results)).toContain("healthy");
  });
});
