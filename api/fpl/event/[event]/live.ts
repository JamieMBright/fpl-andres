import type { VercelRequest, VercelResponse } from "@vercel/node";

import fplProxyHandler from "../../[...path].js";

/** Explicit deep route: Vercel does not reliably dispatch four segments to the catch-all. */
export default function liveGameweekHandler(
  request: VercelRequest,
  response: VercelResponse,
): Promise<void> {
  const rawEvent = request.query.event;
  const event = Array.isArray(rawEvent) ? rawEvent[0] : rawEvent;
  return fplProxyHandler(
    request,
    response,
    `/api/fpl/event/${event ?? "invalid"}/live/`,
  );
}
