import type { VercelRequest, VercelResponse } from "@vercel/node";

import { normalizeVercelProxyUrl } from "../_lib/fpl-path.js";
import { createFplProxyResponse } from "../_lib/fpl-proxy.js";
import {
  applyFailureHeaders,
  logHandlerFailure,
  newRequestId,
} from "../_lib/request-log.js";

export default async function fplProxyHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
  const startedAt = performance.now();
  try {
    const proxyResponse = await createFplProxyResponse(
      normalizeVercelProxyUrl(request.url ?? ""),
      request.method ?? "GET",
    );

    proxyResponse.headers.forEach((value, key) => {
      response.setHeader(key, value);
    });
    const body = Buffer.from(await proxyResponse.arrayBuffer());
    response.status(proxyResponse.status).send(body);
  } catch (error) {
    const requestId = newRequestId();
    logHandlerFailure(requestId, {
      route: "/api/fpl/*",
      error,
      status: 502,
      startedAt,
    });
    applyFailureHeaders(response, requestId);
    response.status(502).send(
      JSON.stringify({
        error: "FPL proxy handler failed unexpectedly.",
        reason: "unreachable",
        requestId,
      }),
    );
  }
}
