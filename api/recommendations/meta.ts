import type { VercelRequest, VercelResponse } from "@vercel/node";

import { recommendationsHandler } from "../_lib/recommendations.js";

const handler = recommendationsHandler("meta");

export default function metaHandler(
  request: VercelRequest,
  response: VercelResponse,
): void {
  handler(request, response);
}
