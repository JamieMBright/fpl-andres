import type { VercelRequest, VercelResponse } from "@vercel/node";

import fplProxyHandler from "../../[...path].js";

/** Explicit deep route: Vercel does not reliably dispatch four segments to the catch-all. */
export default function liveGameweekHandler(
  request: VercelRequest,
  response: VercelResponse,
): Promise<void> {
  return fplProxyHandler(request, response);
}
