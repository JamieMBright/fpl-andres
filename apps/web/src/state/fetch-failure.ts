/**
 * What can go wrong when the browser asks the proxy for something.
 *
 * Audit item #141. Both callers caught `unknown` and narrowed it by hand, with
 * the same `instanceof DOMException && name === "AbortError"` line copied into
 * each. That has two costs. The obvious one is duplication. The one that
 * matters is that `unknown` does not enumerate anything, so neither caller
 * could be checked against the set of things that actually happen, and a new
 * failure -- offline, a 429 from the request budget -- was indistinguishable
 * from the ones already handled.
 *
 * A discriminated union enumerates them. The compiler then knows when a
 * `switch` is missing an arm, which is the whole point: the next failure mode
 * added here becomes a build error at every site that has to decide what to do
 * about it, rather than falling into someone's `default`.
 *
 * Abort is deliberately one of the cases rather than an exception to them. It
 * is not a failure -- the component asked for the request to stop -- but it
 * arrives through the same channel, and leaving it out is exactly how it ends
 * up rendered as an error in the one path that forgot to check.
 */

export type FetchFailure =
  /** The component unmounted or the input changed. Render nothing. */
  | { kind: "aborted" }
  /** No response at all: DNS, TLS, offline, connection dropped. */
  | { kind: "offline" }
  /** The request budget refused it. `retryAfterSeconds` when the server said. */
  | { kind: "rate_limited"; retryAfterSeconds: number | null }
  /** A response arrived and was not a success. */
  | { kind: "http"; status: number }
  /** A success whose body was not the shape the contract requires. */
  | { kind: "contract"; reason: string }
  /** Anything else. Kept last so the others are not a lie by omission. */
  | { kind: "unknown" };

/**
 * Classify whatever a fetch chain threw.
 *
 * `unknown` in, a named case out, in one place rather than at each call site.
 */
export function classifyFetchFailure(caught: unknown): FetchFailure {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return { kind: "aborted" };
  }
  // Both browsers and undici report a failed connection as a plain TypeError
  // with no status and no body. It is the only thing TypeError means here,
  // because a programming error inside the .then() would not reach this.
  if (caught instanceof TypeError) {
    return { kind: "offline" };
  }
  if (caught instanceof FetchResponseError) {
    return caught.failure;
  }
  return { kind: "unknown" };
}

/**
 * A response that arrived and was not usable. Carries the classification rather
 * than a message, so a caller decides what to say rather than being handed
 * words chosen somewhere else.
 */
export class FetchResponseError extends Error {
  override name = "FetchResponseError";
  constructor(readonly failure: FetchFailure) {
    super(`fetch failed: ${failure.kind}`);
  }
}

/**
 * Turn a non-ok response into the case it represents.
 *
 * 429 is separated from other 4xx because it is the only one the caller can do
 * something about, and because this deployment now issues them itself.
 */
export function failureForResponse(response: Response): FetchFailure {
  if (response.status === 429) {
    const header = response.headers.get("Retry-After")?.trim() ?? "";
    // Not `Number(header)` alone: `Number("")` is 0, which is finite and
    // non-negative, so an empty header would become "try again in 0 seconds".
    // The header form is also allowed to be an HTTP date, which is not a
    // number of seconds and must not be read as one.
    const seconds = /^\d+(\.\d+)?$/.test(header) ? Number(header) : Number.NaN;
    return {
      kind: "rate_limited",
      retryAfterSeconds: Number.isFinite(seconds) ? Math.ceil(seconds) : null,
    };
  }
  return { kind: "http", status: response.status };
}

/**
 * One sentence per case, addressed to a person rather than to a log.
 *
 * Exhaustive by construction: adding a case to `FetchFailure` without adding a
 * sentence here is a type error, which is the point of the union.
 */
export function describeFetchFailure(failure: FetchFailure): string {
  switch (failure.kind) {
    case "aborted":
      return "";
    case "offline":
      return "No connection. Check your network and try again.";
    case "rate_limited":
      return failure.retryAfterSeconds === null
        ? "Too many requests. Try again shortly."
        : `Too many requests. Try again in ${failure.retryAfterSeconds} seconds.`;
    case "http":
      return failure.status >= 500
        ? "Fantasy Premier League is not responding. Try again shortly."
        : "That request was refused.";
    case "contract":
      // Never the underlying reason: it names a field, which is a sentence for
      // a maintainer reading a log, not for a manager reading a page.
      return "Fantasy Premier League sent something unexpected.";
    case "unknown":
      return "Something went wrong. Try again shortly.";
  }
}
