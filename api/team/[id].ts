import type { VercelRequest, VercelResponse } from "@vercel/node";

import {
  clientAddress,
  rateLimitHeaders,
  RateLimiter,
  TEAM_STATE_POLICY,
} from "../_lib/rate-limit.js";
import {
  applyFailureHeaders,
  logHandlerFailure,
  logRateLimit,
  newRequestId,
} from "../_lib/request-log.js";
import { createTeamPublicStateResponse } from "../_lib/team-public-state-response.js";

/** See the note in api/fpl/[...path].ts: module state survives a warm instance. */
const limiter = new RateLimiter(TEAM_STATE_POLICY);

export default async function teamPublicStateHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
  const startedAt = performance.now();
  const decision = limiter.check(clientAddress(request.headers));
  for (const [name, value] of Object.entries(
    rateLimitHeaders(TEAM_STATE_POLICY, decision),
  )) {
    response.setHeader(name, value);
  }
  if (!decision.allowed) {
    logRateLimit({ route: "/api/team/:id", scope: decision.scope });
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.setHeader("Cache-Control", "no-store");
    response.status(429).send(
      JSON.stringify({
        status: "degraded",
        reason: "rate_limited",
      }),
    );
    return;
  }
  try {
    const rawId = request.query.id;
    const entryId =
      typeof rawId === "string" && /^\d+$/.test(rawId) ? Number(rawId) : 0;
    const teamResponse = await createTeamPublicStateResponse(
      entryId,
      request.method ?? "GET",
    );

    teamResponse.headers.forEach((value, key) => {
      response.setHeader(key, value);
    });
    response
      .status(teamResponse.status)
      .send(Buffer.from(await teamResponse.arrayBuffer()));
  } catch (error) {
    const requestId = newRequestId();
    logHandlerFailure(requestId, {
      route: "/api/team/:id",
      error,
      status: 503,
      startedAt,
    });
    applyFailureHeaders(response, requestId);
    response.status(503).send(
      JSON.stringify({
        status: "degraded",
        reason: "fpl_source_failed",
        requestId,
      }),
    );
  }
}
