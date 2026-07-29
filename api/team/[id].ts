import type { VercelRequest, VercelResponse } from "@vercel/node";

import { createTeamPublicStateResponse } from "../_lib/team-public-state-response";

export default async function teamPublicStateHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
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
}
