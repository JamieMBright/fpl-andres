import type { VercelRequest, VercelResponse } from "@vercel/node";

import { recommendationsHandler } from "../_lib/recommendations.js";

const handler = recommendationsHandler("markets");

export default function marketsHandler(
  request: VercelRequest,
  response: VercelResponse,
): void {
  handler(request, response);
}
