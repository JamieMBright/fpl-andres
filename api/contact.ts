import type { VercelRequest, VercelResponse } from "@vercel/node";

import { createContactResponse } from "./_lib/contact-response.js";
import { clientAddress } from "./_lib/rate-limit.js";

function firstHeader(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function requestUrl(request: VercelRequest): string {
  const protocol = firstHeader(request.headers["x-forwarded-proto"]) ?? "https";
  const host =
    firstHeader(request.headers["x-forwarded-host"]) ??
    firstHeader(request.headers.host) ??
    "fpl-andres.vercel.app";
  return `${protocol}://${host}${request.url ?? "/api/contact"}`;
}

export default async function contactHandler(
  request: VercelRequest,
  response: VercelResponse,
): Promise<void> {
  const headers = new Headers();
  for (const [name, raw] of Object.entries(request.headers)) {
    const value = firstHeader(raw);
    if (value !== undefined) headers.set(name, value);
  }

  let body: string | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    try {
      body = JSON.stringify(request.body);
    } catch {
      body = "{";
    }
  }

  const result = await createContactResponse(
    new Request(requestUrl(request), {
      method: request.method ?? "GET",
      headers,
      ...(body === undefined ? {} : { body }),
    }),
    { clientKey: clientAddress(request.headers) },
  );

  result.headers.forEach((value, name) => response.setHeader(name, value));
  response.status(result.status).send(Buffer.from(await result.arrayBuffer()));
}
