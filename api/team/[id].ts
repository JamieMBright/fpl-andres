import type { VercelRequest, VercelResponse } from "@vercel/node";

import {
  applyFailureHeaders,
  logHandlerFailure,
  newRequestId,
} from "../_lib/request-log.js";
import { createTeamPublicStateResponse } from "../_lib/team-public-state-response.js";

export default async function teamPublicStateHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
  const startedAt = performance.now();
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
