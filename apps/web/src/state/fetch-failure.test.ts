import { describe, expect, it } from "vitest";

import {
  classifyFetchFailure,
  describeFetchFailure,
  failureForResponse,
  FetchResponseError,
  type FetchFailure,
} from "./fetch-failure";

/**
 * Both callers caught `unknown` and narrowed it by hand, with
 * the same `instanceof DOMException && name === "AbortError"` line copied into
 * each.
 *
 * The duplication was the visible cost. The one that mattered: `unknown`
 * enumerates nothing, so neither caller could be checked against the set of
 * things that actually happen, and a new failure -- offline, a 429 from the
 * request budget this deployment now issues -- was indistinguishable from the
 * ones already handled.
 */

describe("classifyFetchFailure", () => {
  it("names an abort, which is not a failure but arrives the same way", () => {
    const aborted = new DOMException(
      "The operation was aborted.",
      "AbortError",
    );
    expect(classifyFetchFailure(aborted)).toEqual({ kind: "aborted" });
  });

  it("reads a bare TypeError as no connection", () => {
    // Both browsers and undici report a failed connection as a plain
    // TypeError with no status and no body.
    expect(classifyFetchFailure(new TypeError("Failed to fetch"))).toEqual({
      kind: "offline",
    });
  });

  it("passes a classified response failure straight through", () => {
    const failure: FetchFailure = { kind: "http", status: 503 };
    expect(classifyFetchFailure(new FetchResponseError(failure))).toEqual(
      failure,
    );
  });

  it.each([
    ["a plain Error", new Error("boom")],
    ["a string", "boom"],
    ["null", null],
    ["undefined", undefined],
    ["an object", { message: "boom" }],
  ])("falls back to unknown for %s", (_label, thrown) => {
    expect(classifyFetchFailure(thrown)).toEqual({ kind: "unknown" });
  });

  it("does not read a non-abort DOMException as an abort", () => {
    const quota = new DOMException("Quota exceeded", "QuotaExceededError");
    expect(classifyFetchFailure(quota)).toEqual({ kind: "unknown" });
  });
});

describe("failureForResponse", () => {
  it("separates a refusal by the request budget from any other 4xx", () => {
    // It is the only 4xx a caller can do something about, and this deployment
    // now issues them itself.
    const response = new Response(null, {
      status: 429,
      headers: { "Retry-After": "30" },
    });
    expect(failureForResponse(response)).toEqual({
      kind: "rate_limited",
      retryAfterSeconds: 30,
    });
  });

  it("tolerates a 429 with no Retry-After", () => {
    expect(failureForResponse(new Response(null, { status: 429 }))).toEqual({
      kind: "rate_limited",
      retryAfterSeconds: null,
    });
  });

  it.each([
    ["a date-form Retry-After", "Wed, 21 Oct 2026 07:28:00 GMT"],
    ["a negative value", "-5"],
    ["a non-numeric value", "soon"],
    ["an empty value", ""],
  ])("reports no delay rather than a wrong one for %s", (_label, header) => {
    // A wrong number here becomes a countdown shown to a person. Saying
    // nothing is better than counting down from NaN.
    const response = new Response(null, {
      status: 429,
      headers: { "Retry-After": header },
    });
    expect(failureForResponse(response)).toEqual({
      kind: "rate_limited",
      retryAfterSeconds: null,
    });
  });

  it("rounds a fractional delay up, so the client never returns too early", () => {
    const response = new Response(null, {
      status: 429,
      headers: { "Retry-After": "1.2" },
    });
    expect(failureForResponse(response)).toEqual({
      kind: "rate_limited",
      retryAfterSeconds: 2,
    });
  });

  it.each([400, 403, 404, 500, 502, 503])(
    "carries the status for %i",
    (status) => {
      expect(failureForResponse(new Response(null, { status }))).toEqual({
        kind: "http",
        status,
      });
    },
  );
});

describe("describeFetchFailure", () => {
  it("says nothing about an abort, because nothing went wrong", () => {
    expect(describeFetchFailure({ kind: "aborted" })).toBe("");
  });

  it("distinguishes upstream being down from the request being refused", () => {
    expect(describeFetchFailure({ kind: "http", status: 503 })).toContain(
      "not responding",
    );
    expect(describeFetchFailure({ kind: "http", status: 403 })).toContain(
      "refused",
    );
  });

  it("counts down only when the server said how long", () => {
    expect(
      describeFetchFailure({ kind: "rate_limited", retryAfterSeconds: 30 }),
    ).toContain("30 seconds");
    expect(
      describeFetchFailure({ kind: "rate_limited", retryAfterSeconds: null }),
    ).not.toMatch(/\d/);
  });

  it("never shows a manager the contract reason", () => {
    // It names a field. That is a sentence for a maintainer reading a log.
    const message = describeFetchFailure({
      kind: "contract",
      reason: "elements[3].now_cost missing",
    });
    expect(message).not.toContain("now_cost");
    expect(message).not.toContain("elements");
  });

  it("gives every case a sentence", () => {
    const cases: FetchFailure[] = [
      { kind: "aborted" },
      { kind: "offline" },
      { kind: "rate_limited", retryAfterSeconds: null },
      { kind: "http", status: 500 },
      { kind: "contract", reason: "x" },
      { kind: "unknown" },
    ];
    for (const failure of cases) {
      expect(typeof describeFetchFailure(failure)).toBe("string");
    }
  });

  it("ends every sentence it shows with a full stop", () => {
    const shown: FetchFailure[] = [
      { kind: "offline" },
      { kind: "rate_limited", retryAfterSeconds: 5 },
      { kind: "http", status: 500 },
      { kind: "contract", reason: "x" },
      { kind: "unknown" },
    ];
    for (const failure of shown) {
      expect(describeFetchFailure(failure)).toMatch(/\.$/);
    }
  });
});
