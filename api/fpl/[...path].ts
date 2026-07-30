import type { VercelRequest, VercelResponse } from "@vercel/node";

import { normalizeVercelProxyUrl } from "../_lib/fpl-path.js";
import { createFplProxyResponse } from "../_lib/fpl-proxy.js";

export default async function fplProxyHandler(
  request: VercelRequest,
  response: VercelResponse,
) {
  const proxyResponse = await createFplProxyResponse(
    normalizeVercelProxyUrl(request.url ?? ""),
    request.method ?? "GET",
  );

  proxyResponse.headers.forEach((value, key) => {
    response.setHeader(key, value);
  });
  const body = Buffer.from(await proxyResponse.arrayBuffer());
  response.status(proxyResponse.status).send(body);
}
