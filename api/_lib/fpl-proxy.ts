import { FplPathError, resolveFplUpstreamUrl } from "./fpl-path.js";

const FPL_USER_AGENT =
  "FPLAndres/0.5.1 (+https://github.com/JamieMBright/fpl-andres)";
const DEFAULT_LIMIT_BYTES = 5 * 1024 * 1024;
const BOOTSTRAP_LIMIT_BYTES = 8 * 1024 * 1024;
export const FPL_PROXY_BUDGET_MS = 8_500;
const PER_ATTEMPT_TIMEOUT_MS = 4_000;
const MIN_ATTEMPT_BUDGET_MS = 250;
const MAX_ATTEMPTS = 3;
const MAX_RETRY_AFTER_MS = 30_000;
const RETRYABLE_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);

type Sleep = (milliseconds: number) => Promise<void>;

export async function createFplProxyResponse(
  requestUrl: string,
  method: string,
  fetchUpstream: typeof fetch = fetch,
  sleep: Sleep = defaultSleep,
  random: () => number = Math.random,
  now: () => number = Date.now,
  deadline: number = now() + FPL_PROXY_BUDGET_MS,
): Promise<Response> {
  if (method !== "GET") {
    return jsonError("Only GET is supported by the FPL proxy.", 405, {
      Allow: "GET",
    });
  }

  let upstreamUrl: URL;
  try {
    upstreamUrl = resolveFplUpstreamUrl(requestUrl);
  } catch (error) {
    if (error instanceof FplPathError) {
      return jsonError(error.message, 400);
    }
    throw error;
  }

  const upstreamResponse = await fetchWithRetries(
    upstreamUrl,
    fetchUpstream,
    sleep,
    random,
    now,
    deadline,
  );
  if (!upstreamResponse) {
    return jsonError(
      "FPL could not be reached within the request budget.",
      502,
      {},
      "unreachable",
    );
  }

  const limit = upstreamUrl.pathname.endsWith("/bootstrap-static/")
    ? BOOTSTRAP_LIMIT_BYTES
    : DEFAULT_LIMIT_BYTES;
  const declaredLength = parseContentLength(
    upstreamResponse.headers.get("Content-Length"),
  );
  if (declaredLength !== null && declaredLength > limit) {
    await upstreamResponse.body?.cancel();
    return jsonError(
      "FPL returned a response larger than the allowed limit.",
      502,
      {},
      "oversize",
    );
  }

  const contentType = upstreamResponse.headers.get("Content-Type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    await upstreamResponse.body?.cancel();
    return jsonError(
      "FPL returned an unexpected response format.",
      502,
      {},
      "unexpected_format",
    );
  }

  let body: Uint8Array | null;
  try {
    body = await readBoundedBody(upstreamResponse, limit);
  } catch {
    return jsonError(
      "FPL could not be reached within the request budget.",
      502,
      {},
      "unreachable",
    );
  }
  if (!body) {
    return jsonError(
      "FPL returned a response larger than the allowed limit.",
      502,
      {},
      "oversize",
    );
  }

  const responseBody = new ArrayBuffer(body.byteLength);
  new Uint8Array(responseBody).set(body);
  return new Response(responseBody, {
    status: upstreamResponse.status,
    headers: {
      "Cache-Control": cachePolicyFor(upstreamUrl.pathname),
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

async function fetchWithRetries(
  upstreamUrl: URL,
  fetchUpstream: typeof fetch,
  sleep: Sleep,
  random: () => number,
  now: () => number,
  deadline: number,
): Promise<Response | null> {
  const trace = globalThis.crypto.randomUUID();
  const attemptFailures: string[] = [];
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    const remaining = deadline - now();
    if (remaining < MIN_ATTEMPT_BUDGET_MS) {
      return null;
    }

    try {
      const response = await fetchUpstream(upstreamUrl, {
        method: "GET",
        headers: {
          Accept: "application/json",
          "Accept-Encoding": "gzip",
          "User-Agent": FPL_USER_AGENT,
        },
        redirect: "error",
        signal: AbortSignal.timeout(
          Math.max(1, Math.min(PER_ATTEMPT_TIMEOUT_MS, remaining)),
        ),
      });

      if (
        !RETRYABLE_STATUSES.has(response.status) ||
        attempt === MAX_ATTEMPTS - 1
      ) {
        return response;
      }

      const delay = retryDelay(
        response.headers.get("Retry-After"),
        attempt,
        random,
        now,
      );
      if (delay + MIN_ATTEMPT_BUDGET_MS > deadline - now()) {
        return response;
      }
      await response.body?.cancel();
      await sleep(delay);
    } catch (error) {
      // A request that succeeds on attempt three used to leave no evidence that
      // the first two failed, so a degrading upstream looked healthy. One line
      // per attempt, correlated by trace, and a timeout named as a timeout
      // rather than collapsed into 'unreachable'.
      attemptFailures.push(
        error instanceof DOMException && error.name === "TimeoutError"
          ? "timeout"
          : `${error instanceof Error ? error.name : "unknown"}`,
      );
      if (attempt === MAX_ATTEMPTS - 1) {
        console.warn(
          JSON.stringify({
            level: "warn",
            event: "upstream_exhausted",
            trace,
            url: upstreamUrl,
            attempts: MAX_ATTEMPTS,
            failures: attemptFailures,
          }),
        );
        return null;
      }
      const delay = retryDelay(null, attempt, random, now);
      if (delay + MIN_ATTEMPT_BUDGET_MS > deadline - now()) {
        console.warn(
          JSON.stringify({
            level: "warn",
            event: "upstream_budget_exhausted",
            trace,
            url: upstreamUrl,
            attempts: attempt + 1,
            failures: attemptFailures,
          }),
        );
        return null;
      }
      await sleep(delay);
    }
  }

  return null;
}

function retryDelay(
  retryAfter: string | null,
  attempt: number,
  random: () => number,
  now: () => number,
): number {
  if (retryAfter && /^\d+$/.test(retryAfter)) {
    return Math.min(Number(retryAfter) * 1_000, MAX_RETRY_AFTER_MS);
  }
  if (retryAfter) {
    const retryAt = Date.parse(retryAfter);
    if (Number.isFinite(retryAt)) {
      return Math.min(Math.max(0, retryAt - now()), MAX_RETRY_AFTER_MS);
    }
    return MAX_RETRY_AFTER_MS;
  }

  const exponential = 500 * 2 ** attempt;
  const jitter = 0.8 + random() * 0.4;
  return Math.round(exponential * jitter);
}

async function readBoundedBody(
  response: Response,
  limit: number,
): Promise<Uint8Array | null> {
  if (!response.body) {
    return new Uint8Array();
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      total += value.byteLength;
      if (total > limit) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

function defaultSleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function parseContentLength(rawValue: string | null): number | null {
  if (rawValue === null) {
    return null;
  }
  if (!/^\d+$/.test(rawValue)) {
    return null;
  }
  const value = Number(rawValue);
  return Number.isSafeInteger(value) ? value : null;
}

function cachePolicyFor(pathname: string): string {
  if (
    pathname.endsWith("/bootstrap-static/") ||
    pathname.endsWith("/fixtures/")
  ) {
    return "public, s-maxage=60, stale-while-revalidate=300";
  }
  if (pathname.includes("/element-summary/")) {
    return "public, s-maxage=300, stale-while-revalidate=600";
  }
  return "private, no-store";
}

function jsonError(
  message: string,
  status: number,
  additionalHeaders: Record<string, string> = {},
  reason?: FplProxyErrorReason,
): Response {
  const body: Record<string, string> = { error: message };
  if (reason) body.reason = reason;
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      ...additionalHeaders,
    },
  });
}

export type FplProxyErrorReason =
  "unreachable" | "unexpected_format" | "oversize";
