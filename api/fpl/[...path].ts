import type { VercelRequest, VercelResponse } from "@vercel/node";

import { normalizeVercelProxyUrl } from "../_lib/fpl-path.js";
import { createFplProxyResponse } from "../_lib/fpl-proxy.js";
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

export default async function fplProxyHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
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
      normalizeVercelProxyUrl(request.url ?? ""),
      request.method ?? "GET",
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
