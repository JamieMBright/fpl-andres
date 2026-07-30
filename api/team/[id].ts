import type { VercelRequest, VercelResponse } from "@vercel/node";

import { createTeamPublicStateResponse } from "../_lib/team-public-state-response.js";

export default async function teamPublicStateHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
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
    const message = error instanceof Error ? error.message : String(error);
    console.error("teamPublicStateHandler crash:", error);
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.setHeader("Cache-Control", "no-store");
    response.setHeader(
      "x-fpl-andres-debug",
      message.slice(0, 300).replace(/[^\x20-\x7e]/g, "?"),
    );
    response.status(503).send(
      JSON.stringify({
        status: "degraded",
        reason: "fpl_source_failed",
      }),
    );
  }
}
