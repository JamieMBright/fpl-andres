import type { VercelRequest, VercelResponse } from "@vercel/node";

import { recommendationsHandler } from "../_lib/recommendations.js";

const handler = recommendationsHandler("latest");

export default function latestHandler(
  request: VercelRequest,
  response: VercelResponse,
): void {
  handler(request, response);
}
