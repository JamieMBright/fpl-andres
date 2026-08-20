import type { VercelRequest, VercelResponse } from "@vercel/node";

import { recommendationsHandler } from "../_lib/recommendations.js";

const handler = recommendationsHandler("xstart");

export default function xstartHandler(
  request: VercelRequest,
  response: VercelResponse,
): void {
  handler(request, response);
}
