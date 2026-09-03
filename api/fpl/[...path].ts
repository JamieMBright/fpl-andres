import type { VercelRequest, VercelResponse } from "@vercel/node";

import { FplDocumentStore } from "../_lib/fpl-document-store.js";
import { normalizeVercelProxyUrl } from "../_lib/fpl-path.js";
import {
  createFplProxyResponse,
  type FplProxyOutcome,
} from "../_lib/fpl-proxy.js";
import { SourceCache } from "../_lib/source-cache.js";
import {
  clientAddress,
  FPL_PROXY_POLICY,
  rateLimitHeaders,
  RateLimiter,
} from "../_lib/rate-limit.js";
import {
  applyFailureHeaders,
  logHandlerFailure,
  logRateLimit,
  newRequestId,
} from "../_lib/request-log.js";

/**
 * Module scope on purpose: the counters have to outlive the invocation to mean
 * anything, and a warm serverless instance keeps module state between requests.
 */
const limiter = new RateLimiter(FPL_PROXY_POLICY);

/**
 * Same reasoning as the limiter, for the same reason it is here rather than
 * inside the request. The cache coalesces concurrent identical reads and holds
 * a public document for its short TTL; the store keeps the last known-good
 * copy of one for hours, so an FPL outage degrades the page instead of
 * emptying it. Both are per-instance, which is all a warm serverless function
 * can offer -- and enough for the incident that actually happens.
 */
const cache = new SourceCache<FplProxyOutcome>();
const store = new FplDocumentStore();

/** Test seam. Production code has no reason to call this. */
export function resetFplProxyState(): void {
  cache.clear();
  store.clear();
}

export default async function fplProxyHandler(
  request: VercelRequest,
  response: VercelResponse,
  canonicalRequestUrl: string = request.url ?? "",
): Promise<void> {
  const startedAt = performance.now();
  const decision = limiter.check(clientAddress(request.headers));
  for (const [name, value] of Object.entries(
    rateLimitHeaders(FPL_PROXY_POLICY, decision),
  )) {
    response.setHeader(name, value);
  }
  if (!decision.allowed) {
    logRateLimit({ route: "/api/fpl/*", scope: decision.scope });
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.setHeader("Cache-Control", "no-store");
    response.status(429).send(
      JSON.stringify({
        error: "Too many requests. Try again shortly.",
        reason: "rate_limited",
      }),
    );
    return;
  }
  try {
    const proxyResponse = await createFplProxyResponse(
      normalizeVercelProxyUrl(canonicalRequestUrl),
      request.method ?? "GET",
      fetch,
      undefined,
      undefined,
      undefined,
      undefined,
      {
        cache,
        store,
        onOutcome: ({ url, tier, status, staleAgeMs }) => {
          // A stale answer renders identically to a fresh one, which is the
          // point -- and exactly why it has to be visible here. Without the
          // tier, a permanently broken upstream looks like a healthy service.
          const line = JSON.stringify({
            level: tier === "fresh" || tier === "reused" ? "info" : "warn",
            event: "fpl_proxy_tier",
            route: "/api/fpl/*",
            url,
            tier,
            status,
            staleAgeMs,
          });
          if (tier === "fresh" || tier === "reused") console.log(line);
          else console.warn(line);
        },
      },
    );

    proxyResponse.headers.forEach((value, key) => {
      response.setHeader(key, value);
    });
    const body = Buffer.from(await proxyResponse.arrayBuffer());
    response.status(proxyResponse.status).send(body);
  } catch (error) {
    const requestId = newRequestId();
    logHandlerFailure(requestId, {
      route: "/api/fpl/*",
      error,
      status: 502,
      startedAt,
    });
    applyFailureHeaders(response, requestId);
    response.status(502).send(
      JSON.stringify({
        error: "FPL proxy handler failed unexpectedly.",
        reason: "unreachable",
        requestId,
      }),
    );
  }
}
