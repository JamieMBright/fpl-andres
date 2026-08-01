/**
 * Failure reporting for the serverless handlers.
 *
 * An unexpected throw used to put the first 300 characters of the exception
 * message into an `x-fpl-andres-debug` response header, which every client
 * received. Exception text can carry stack-frame paths, upstream hostnames and
 * fragments of payload, so it belongs in the server log rather than on the
 * public edge. The client now gets an opaque id it can quote, and the detail
 * stays behind it.
 */

const REQUEST_ID_HEADER = "x-fpl-andres-request-id";

export type HandlerFailure = {
  route: string;
  error: unknown;
  status: number;
  startedAt?: number;
};

export type FailureHeaders = {
  setHeader(name: string, value: string): unknown;
};

/** Opaque, unguessable, and cheap enough to mint on every failure. */
export function newRequestId(): string {
  return globalThis.crypto.randomUUID();
}

/**
 * One structured line per failure, so a log search can pivot on any field.
 * Emitted as JSON because a serverless log drain parses that and not prose.
 */
export function logHandlerFailure(
  requestId: string,
  { route, error, status, startedAt }: HandlerFailure,
): void {
  console.error(
    JSON.stringify({
      level: "error",
      event: "handler_failure",
      requestId,
      route,
      status,
      durationMs:
        startedAt === undefined
          ? null
          : Math.round(performance.now() - startedAt),
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : null,
    }),
  );
}

/**
 * Headers for a failed response: the correlation id, no caching, and nosniff so
 * an error body cannot be re-interpreted as another content type.
 */
export function applyFailureHeaders(
  response: FailureHeaders,
  requestId: string,
): void {
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader(REQUEST_ID_HEADER, requestId);
}

export { REQUEST_ID_HEADER };

/**
 * Timing and upstream outcomes, so a failure is visible before a user reports it.
 *
 * Audit items #85, #92 and #93. There was no timing instrumentation and a
 * contract failure was swallowed without recording what upstream had actually
 * said, so a spike in 502s or an FPL schema change was invisible until someone
 * complained, and then not reproducible.
 *
 * The sink is stdout and stderr. That is not a limitation: Vercel drains both,
 * and every hosted log service ingests newline-delimited JSON. Choosing a
 * vendor is an owner decision; emitting a line an alert can be written against
 * is not, and it is the part that has to exist first. `docs/OPERATIONS.md`
 * records the queries.
 *
 * Nothing here may carry a payload fragment, an upstream body or a header
 * value. Status codes, durations, counts and fixed strings only -- the same
 * rule that produced the opaque request id above.
 */

/**
 * A refusal is a signal, not an error. It is logged so the rate of refusals is
 * visible: a steady trickle is the limit working, and a step change is either
 * an attack or a limit set too low, which look identical in a 429 count alone.
 */
export function logRateLimit({
  route,
  scope,
}: {
  route: string;
  scope: "client" | "global";
}): void {
  console.warn(
    JSON.stringify({
      level: "warn",
      event: "rate_limited",
      route,
      scope,
    }),
  );
}

export type UpstreamOutcome = {
  requestId: string;
  route: string;
  source: string;
  status: number | null;
  reason: string | null;
  durationMs: number;
  attempts?: number;
  /** True when nothing was fetched: served from cache or a shared flight. */
  reused?: boolean;
};

export function logUpstreamOutcome({
  requestId,
  route,
  source,
  status,
  reason,
  durationMs,
  attempts,
  reused,
}: UpstreamOutcome): void {
  const failed = status === null || status >= 500 || reason !== null;
  const line = JSON.stringify({
    level: failed ? "warn" : "info",
    event: "upstream_outcome",
    requestId,
    route,
    source,
    status,
    reason,
    durationMs: Math.round(durationMs),
    attempts: attempts ?? null,
    reused: reused ?? false,
  });
  if (failed) console.warn(line);
  else console.log(line);
}

export type HandlerOutcome = {
  requestId: string;
  route: string;
  status: number;
  reason: string | null;
  totalMs: number;
  upstreamMs: number;
};

/**
 * The split matters more than the total. A slow handler that spent its time
 * waiting on FPL is a different problem from one that spent it parsing, and
 * only one of the two is ours to fix.
 */
export function logHandlerOutcome({
  requestId,
  route,
  status,
  reason,
  totalMs,
  upstreamMs,
}: HandlerOutcome): void {
  const total = Math.round(totalMs);
  const upstream = Math.round(upstreamMs);
  const line = JSON.stringify({
    level: status >= 500 ? "warn" : "info",
    event: "handler_outcome",
    requestId,
    route,
    status,
    reason,
    totalMs: total,
    upstreamMs: upstream,
    // Never negative: a clock that went backwards is not evidence of negative work.
    localMs: Math.max(0, total - upstream),
  });
  if (status >= 500) console.warn(line);
  else console.log(line);
}
