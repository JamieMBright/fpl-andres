import type { VercelRequest, VercelResponse } from "@vercel/node";

import { normalizeVercelProxyUrl } from "../_lib/fpl-path.js";
import { createFplProxyResponse } from "../_lib/fpl-proxy.js";

export default async function fplProxyHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
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
    const message = error instanceof Error ? error.message : String(error);
    console.error("fplProxyHandler crash:", error);
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.setHeader("Cache-Control", "no-store");
    response.setHeader(
      "x-fpl-andres-debug",
      message.slice(0, 300).replace(/[^\x20-\x7e]/g, "?"),
    );
    response.status(502).send(
      JSON.stringify({
        error: "FPL proxy handler failed unexpectedly.",
        reason: "unreachable",
      }),
    );
  }
}
