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
