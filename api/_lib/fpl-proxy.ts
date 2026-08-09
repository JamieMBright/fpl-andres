import type { FplDocumentStore } from "./fpl-document-store.js";
import { FplPathError, resolveFplUpstreamUrl } from "./fpl-path.js";
import { logProxyRefusal } from "./request-log.js";
import type { SourceCache } from "./source-cache.js";

/**
 * Name and a contact URL, and a version that does not move on
 * every release.
 *
 * A patch-level version is a fingerprint: it changes with each deploy, so an
 * upstream log can distinguish one build of this project from another and, over
 * time, watch it. The minor version is enough for anyone who needs to tell a
 * behaviour change from a client, and the URL is the part that actually
 * matters -- it is how the Premier League would reach somebody if this client
 * were doing something it should not.
 *
 * Kept identical to `FPL_USER_AGENT` in `adapters/fpl.py`, because the two
 * clients speak to the same upstream and two spellings would look like two
 * projects.
 */
const FPL_USER_AGENT =
  "FPLAndres/0.5 (+https://github.com/JamieMBright/fpl-andres)";
const DEFAULT_LIMIT_BYTES = 5 * 1024 * 1024;
const BOOTSTRAP_LIMIT_BYTES = 8 * 1024 * 1024;

/**
 * The whole-request budget.
 *
 * `vercel.json` allows this function fifteen seconds. It used to stop itself at
 * eight and a half, which meant a cold instance reading a three-megabyte
 * bootstrap over a fresh connection could run out of budget while the upstream
 * was still answering perfectly well -- a self-inflicted 502 with six unused
 * seconds left on the clock. Twelve keeps a three-second margin, so the proxy
 * still returns a described error rather than being killed mid-flight.
 */
export const FPL_PROXY_BUDGET_MS = 12_000;

/**
 * Bootstrap is not like the other endpoints: it is megabytes rather than
 * kilobytes, and a first read on a cold connection legitimately takes longer
 * than four seconds. Giving it the same per-attempt timeout as a fixture list
 * turned a slow success into three cancelled attempts and a 502.
 */
const PER_ATTEMPT_TIMEOUT_MS = 4_000;
const BOOTSTRAP_ATTEMPT_TIMEOUT_MS = 7_000;
const MIN_ATTEMPT_BUDGET_MS = 250;

/**
 * A retry is only worth starting if there is time for it to finish. Checking
 * only that the backoff fits meant the proxy could sleep, fire a second
 * attempt with two hundred milliseconds left, and abort it -- spending the
 * remaining budget to guarantee a failure. The delay and a usable attempt
 * window both have to fit.
 */
const MIN_RETRY_ATTEMPT_MS = 1_500;
const MAX_ATTEMPTS = 3;
const MAX_RETRY_AFTER_MS = 30_000;
/**
 * 403 is here on evidence. Measured against production on 2026-08-09, FPL
 * answered 403 with no content type to this deployment and then served five
 * consecutive requests from the same region moments later. Treating one as
 * final spent a whole page load on a refusal that had already lifted.
 */
const RETRYABLE_STATUSES = new Set([403, 408, 425, 429, 500, 502, 503, 504]);

/**
 * How long a public document may be reused without asking FPL again.
 *
 * The numbers match `cachePolicyFor` below, because two layers disagreeing
 * about how stale the same bytes are allowed to be is a bug waiting to be
 * found in production. Zero means "never reuse": every per-manager path falls
 * here by default, so a new allowlisted endpoint in `fpl-path.ts` is private
 * until somebody names it public, rather than the other way round.
 */
export function publicTtlMsFor(pathname: string): number {
  if (
    pathname.endsWith("/bootstrap-static/") ||
    pathname.endsWith("/fixtures/")
  ) {
    return 60_000;
  }
  if (pathname.includes("/element-summary/")) {
    return 300_000;
  }
  return 0;
}

/**
 * How long a copy may be held as an answer of last resort when FPL will not
 * answer at all. Separate from `publicTtlMsFor`, which asks the different
 * question of whether a document may be reused instead of asking.
 *
 * A manager's history is the past seasons, which are settled and never change
 * again, so an hours-old copy is old rather than wrong. That is not true of
 * anything else per-manager: the entry and the picks both move at the
 * deadline, and yesterday's squad is a wrong answer dressed as an old one.
 * Retention here never makes a document shareable — `cachePolicyFor` still
 * marks every per-manager path `private, no-store`.
 */
export function retentionMsFor(pathname: string): number {
  if (pathname.endsWith("/history/")) {
    return 6 * 60 * 60 * 1_000;
  }
  return publicTtlMsFor(pathname);
}

type Sleep = (milliseconds: number) => Promise<void>;

/**
 * Which tier answered. Logged so that a working fallback cannot hide a
 * degrading upstream: a page that renders from a six-minute-old bootstrap
 * looks identical to a healthy one from the outside.
 */
export type FplProxyTier = "fresh" | "reused" | "stale" | "failed";

/**
 * The result of one upstream read, in a form that can be shared between
 * callers. Not a `Response`: its body can only be read once, and coalescing
 * exists precisely so that several callers read the same bytes.
 */
export type FplProxyOutcome =
  | { kind: "ok"; status: number; body: ArrayBuffer }
  | {
      kind: "error";
      status: number;
      message: string;
      reason: FplProxyErrorReason;
      /** What FPL actually answered, where it answered at all. */
      upstreamStatus?: number;
      upstreamMediaType?: string;
    };

export interface FplProxyDependencies {
  /** Coalesces concurrent identical reads and holds public ones for their TTL. */
  cache?: SourceCache<FplProxyOutcome>;
  /** The last known-good copy of each public document. */
  store?: FplDocumentStore;
  /** Called once per request with the tier that answered. */
  onOutcome?: (event: {
    url: string;
    tier: FplProxyTier;
    status: number;
    staleAgeMs: number | null;
  }) => void;
}

export async function createFplProxyResponse(
  requestUrl: string,
  method: string,
  fetchUpstream: typeof fetch = fetch,
  sleep: Sleep = defaultSleep,
  random: () => number = Math.random,
  now: () => number = Date.now,
  deadline: number = now() + FPL_PROXY_BUDGET_MS,
  dependencies: FplProxyDependencies = {},
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

  const { cache, store, onOutcome } = dependencies;
  const ttlMs = publicTtlMsFor(upstreamUrl.pathname);
  const retainMs = retentionMsFor(upstreamUrl.pathname);
  const key = upstreamUrl.href;
  const read = () =>
    readUpstream(upstreamUrl, fetchUpstream, sleep, random, now, deadline);

  let outcome: FplProxyOutcome;
  let reused = false;
  if (cache) {
    const resolved = await cache.resolve(
      key,
      ttlMs,
      read,
      // Only a document is worth holding. An error, or a 404 that will become a
      // 200 the moment FPL finishes deploying, is not -- caching either would
      // mean serving one bad second for a whole minute.
      (value) => value.kind === "ok" && value.status === 200,
    );
    outcome = resolved.value;
    reused = resolved.reused;
  } else {
    outcome = await read();
  }

  if (outcome.kind === "ok") {
    if (store && retainMs > 0 && outcome.status === 200) {
      store.put(key, outcome.body);
    }
    onOutcome?.({
      url: key,
      tier: reused ? "reused" : "fresh",
      status: outcome.status,
      staleAgeMs: null,
    });
    // The body was copied into a fresh ArrayBuffer before being
    // returned. `readBoundedBody` now assembles into one directly, so the copy
    // is gone -- it duplicated up to eight megabytes of bootstrap per request.
    return new Response(outcome.body, {
      status: outcome.status,
      headers: {
        "Cache-Control": cachePolicyFor(upstreamUrl.pathname),
        "Content-Type": "application/json; charset=utf-8",
      },
    });
  }

  // FPL did not answer. For a document that is the same for every caller, a
  // copy from a few minutes ago answers the reader's question; a 502 answers
  // nothing. The copy goes out labelled, never disguised as current.
  const retained = retainMs > 0 ? (store?.get(key) ?? null) : null;
  if (retained) {
    const staleAgeMs = Math.max(0, now() - retained.capturedAt);
    onOutcome?.({ url: key, tier: "stale", status: 200, staleAgeMs });
    return new Response(retained.body, {
      status: 200,
      headers: {
        // A stale per-manager copy is still one manager's, so it follows the
        // same policy as a fresh one rather than a public shelf life.
        "Cache-Control": staleCachePolicyFor(upstreamUrl.pathname),
        "Content-Type": "application/json; charset=utf-8",
        "X-FPL-Stale": "1",
        "X-FPL-Stale-Age": String(Math.round(staleAgeMs / 1_000)),
        "X-FPL-Captured-At": new Date(retained.capturedAt).toISOString(),
      },
    });
  }

  onOutcome?.({
    url: key,
    tier: "failed",
    status: outcome.status,
    staleAgeMs: null,
  });
  return jsonError(outcome.message, outcome.status, {}, outcome.reason);
}

/**
 * One upstream read, reduced to bytes or to a named failure.
 *
 * Split out of `createFplProxyResponse` so that the same read can be shared by
 * coalesced callers and retained as a last-known-good copy. A `Response` could
 * be neither.
 */
async function readUpstream(
  upstreamUrl: URL,
  fetchUpstream: typeof fetch,
  sleep: Sleep,
  random: () => number,
  now: () => number,
  deadline: number,
): Promise<FplProxyOutcome> {
  const isBootstrap = upstreamUrl.pathname.endsWith("/bootstrap-static/");
  const upstreamResponse = await fetchWithRetries(
    upstreamUrl,
    fetchUpstream,
    sleep,
    random,
    now,
    deadline,
    isBootstrap ? BOOTSTRAP_ATTEMPT_TIMEOUT_MS : PER_ATTEMPT_TIMEOUT_MS,
  );
  if (!upstreamResponse) {
    return unreachableOutcome();
  }

  const limit = isBootstrap ? BOOTSTRAP_LIMIT_BYTES : DEFAULT_LIMIT_BYTES;
  const declaredLength = parseContentLength(
    upstreamResponse.headers.get("Content-Length"),
  );
  if (declaredLength !== null && declaredLength > limit) {
    await upstreamResponse.body?.cancel();
    return oversizeOutcome();
  }

  if (!isJsonMediaType(upstreamResponse.headers.get("Content-Type"))) {
    return await refusalOutcome(upstreamResponse);
  }

  let body: ArrayBuffer | null;
  try {
    body = await readBoundedBody(upstreamResponse, limit);
  } catch {
    return unreachableOutcome();
  }
  if (!body) {
    return oversizeOutcome();
  }

  return { kind: "ok", status: upstreamResponse.status, body };
}

/**
 * What FPL actually said, when what it said was not JSON.
 *
 * "Unexpected response format" was true and useless. It threw the body away
 * unread and never looked at the status, so a 403 refusal, a 503 maintenance
 * page and a bot challenge all arrived as the same sentence — and the one
 * thing an operator needs to know, which of those it was, was the one thing
 * nobody had written down.
 *
 * The status and the media type are reported. A short prefix of the body is
 * read too, because a challenge page and a maintenance page both return HTML
 * and only the words tell them apart; it is logged and classified server-side
 * and never returned, since an upstream body is not ours to forward.
 */
async function refusalOutcome(
  upstreamResponse: Response,
): Promise<FplProxyOutcome> {
  const mediaType =
    upstreamResponse.headers.get("Content-Type")?.split(";", 1)[0]?.trim() ??
    "none";
  const prefix = await readPrefix(upstreamResponse, _REFUSAL_PREFIX_BYTES);
  const reason = classifyRefusal(upstreamResponse.status, prefix);
  logProxyRefusal({
    upstreamStatus: upstreamResponse.status,
    mediaType,
    reason,
    // Bounded, stripped of anything that could carry a token, and server-only.
    excerpt: prefix.replace(/\s+/g, " ").slice(0, 200),
  });
  return {
    kind: "error",
    status: 502,
    message: refusalMessage(upstreamResponse.status, mediaType, reason),
    reason,
    upstreamStatus: upstreamResponse.status,
    upstreamMediaType: mediaType,
  };
}

/** Enough to see a title or a Cloudflare ray, far short of a document. */
const _REFUSAL_PREFIX_BYTES = 2_048;

async function readPrefix(response: Response, bytes: number): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) return "";
  try {
    const { value } = await reader.read();
    return new TextDecoder().decode(value?.slice(0, bytes));
  } catch {
    return "";
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}

/**
 * Which refusal this is, from the status and the words in the page.
 *
 * Ordered by how specific the evidence is: a status code that only ever means
 * one thing decides it, and the body is read only where the status is
 * ambiguous — a bot challenge is commonly served as 200, 403 or 503, so the
 * page itself is the only thing that separates it from real maintenance.
 */
function classifyRefusal(status: number, body: string): FplProxyErrorReason {
  const text = body.toLowerCase();
  const challenged =
    text.includes("cf-browser-verification") ||
    text.includes("just a moment") ||
    text.includes("attention required") ||
    text.includes("cf-chl") ||
    text.includes("enable javascript and cookies");
  if (challenged) return "challenged";
  if (status === 429) return "rate_limited";
  if (status === 401 || status === 403) return "refused";
  if (status === 503 || status === 502 || status === 504)
    return "upstream_down";
  return "unexpected_format";
}

function refusalMessage(
  status: number,
  mediaType: string,
  reason: FplProxyErrorReason,
): string {
  const said = `FPL answered ${String(status)} with ${mediaType}`;
  switch (reason) {
    case "challenged":
      return `${said}: a bot challenge, so this deployment is being screened rather than served.`;
    case "rate_limited":
      return `${said}: this deployment is being rate limited by FPL.`;
    case "refused":
      return `${said}: FPL refused the request from this deployment.`;
    case "upstream_down":
      return `${said}: FPL is not serving the API right now.`;
    default:
      return `${said}, which is not JSON.`;
  }
}

function unreachableOutcome(): FplProxyOutcome {
  return {
    kind: "error",
    status: 502,
    message: "FPL could not be reached within the request budget.",
    reason: "unreachable",
  };
}

function oversizeOutcome(): FplProxyOutcome {
  return {
    kind: "error",
    status: 502,
    message: "FPL returned a response larger than the allowed limit.",
    reason: "oversize",
  };
}

async function fetchWithRetries(
  upstreamUrl: URL,
  fetchUpstream: typeof fetch,
  sleep: Sleep,
  random: () => number,
  now: () => number,
  deadline: number,
  attemptTimeoutMs: number,
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
          Math.max(1, Math.min(attemptTimeoutMs, remaining)),
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
      if (delay + MIN_RETRY_ATTEMPT_MS > deadline - now()) {
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
      if (delay + MIN_RETRY_ATTEMPT_MS > deadline - now()) {
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
): Promise<ArrayBuffer | null> {
  if (!response.body) {
    return new ArrayBuffer(0);
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

  // Allocated as an ArrayBuffer rather than as a Uint8Array,
  // so the caller can hand it to `Response` without a second copy.
  //
  // The copy that used to be there was not superstition: `Uint8Array.buffer`
  // is typed `ArrayBufferLike`, which includes SharedArrayBuffer, and
  // `BodyInit` does not accept a shared one. Assembling into an ArrayBuffer
  // here makes the type honest instead of asserting past it, and removes a
  // duplication of up to eight megabytes of bootstrap per request.
  const buffer = new ArrayBuffer(total);
  const body = new Uint8Array(buffer);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return buffer;
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

/**
 * Match the media type, not the whole header.
 *
 * This reported this check as missing. It was not: the presence and
 * value were already checked. It was checked with `includes`, though, which
 * accepts `text/html; charset=application/json` -- contrived, but the strict
 * form costs nothing. Only the part before the first `;` is the media type, and
 * only `application/json` or an `+json` suffix is JSON.
 */
function isJsonMediaType(rawValue: string | null): boolean {
  if (rawValue === null) return false;
  const mediaType = rawValue.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  return mediaType === "application/json" || mediaType.endsWith("+json");
}

/**
 * Only the endpoints whose response is the same for every caller are public.
 *
 * It was asked for entry-specific responses to be distinguished from
 * public ones. They already were, by construction: this is an allow-list of two
 * shapes and everything else -- every `entry/`, `picks/` and `leagues-classic/`
 * path -- falls through to `private, no-store`. A shared CDN is never offered
 * one manager's state to hold, so it cannot hand it to another.
 *
 * The default is the safe one deliberately. A new allowlisted endpoint in
 * `fpl-path.ts` becomes uncacheable rather than becoming public.
 */
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

/** A shorter shelf life for a copy that is already known to be behind. */
function staleCachePolicyFor(pathname: string): string {
  const fresh = cachePolicyFor(pathname);
  return fresh.startsWith("public")
    ? "public, s-maxage=30, stale-while-revalidate=600"
    : fresh;
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
  | "unreachable"
  | "unexpected_format"
  | "oversize"
  /** FPL served a bot challenge instead of the API. */
  | "challenged"
  /** FPL refused this caller outright: 401 or 403. */
  | "refused"
  /** FPL asked this caller to slow down: 429. */
  | "rate_limited"
  /** FPL's own API is down: 502, 503 or 504. */
  | "upstream_down";
