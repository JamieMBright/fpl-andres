import { z } from "zod";

import { CONTACT_POLICY, rateLimitHeaders, RateLimiter } from "./rate-limit.js";
import { newRequestId } from "./request-log.js";

const RESEND_ENDPOINT = "https://api.resend.com/emails";
const MAX_BODY_BYTES = 20 * 1024;
const SUBJECT = "FPL Andres contact";

const contactSchema = z
  .object({
    submissionId: z.uuid(),
    email: z.email().max(254),
    message: z.string().trim().min(20).max(4000),
    website: z.string().max(500),
  })
  .strict();

const limiter = new RateLimiter(CONTACT_POLICY);

export interface ContactEnvironment {
  RESEND_API_KEY?: string;
  CONTACT_FROM_EMAIL?: string;
  CONTACT_TO_EMAIL?: string;
}

export interface ContactOptions {
  clientKey: string;
  env?: ContactEnvironment;
  fetchApi?: typeof fetch;
}

function json(body: unknown, status: number, headers?: HeadersInit): Response {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...headers,
    },
  });
}

function isJson(request: Request): boolean {
  return (
    request.headers
      .get("content-type")
      ?.split(";", 1)[0]
      ?.trim()
      .toLowerCase() === "application/json"
  );
}

function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).origin === new URL(request.url).origin;
  } catch {
    return false;
  }
}

function mailConfiguration(
  env: ContactEnvironment,
): Required<ContactEnvironment> | null {
  const RESEND_API_KEY = env.RESEND_API_KEY?.trim();
  const CONTACT_FROM_EMAIL = env.CONTACT_FROM_EMAIL?.trim();
  const CONTACT_TO_EMAIL = env.CONTACT_TO_EMAIL?.trim();
  return RESEND_API_KEY && CONTACT_FROM_EMAIL && CONTACT_TO_EMAIL
    ? { RESEND_API_KEY, CONTACT_FROM_EMAIL, CONTACT_TO_EMAIL }
    : null;
}

export async function createContactResponse(
  request: Request,
  { clientKey, env = process.env, fetchApi = fetch }: ContactOptions,
): Promise<Response> {
  if (request.method !== "POST") {
    return json({ error: "Use POST.", reason: "method" }, 405, {
      Allow: "POST",
    });
  }
  if (!isJson(request)) {
    return json(
      { error: "Send a JSON request.", reason: "unsupported_media_type" },
      415,
    );
  }
  if (!sameOrigin(request)) {
    return json(
      { error: "That origin is not allowed.", reason: "origin" },
      403,
    );
  }

  const raw = await request.text();
  if (Buffer.byteLength(raw) > MAX_BODY_BYTES) {
    return json(
      { error: "The request is too large.", reason: "payload_too_large" },
      413,
    );
  }

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return json(
      { error: "That request cannot be read.", reason: "invalid_request" },
      400,
    );
  }

  const decision = limiter.check(clientKey);
  const limitHeaders = rateLimitHeaders(CONTACT_POLICY, decision);
  if (!decision.allowed) {
    return json(
      {
        error: "Too many messages. Try again shortly.",
        reason: "rate_limited",
      },
      429,
      limitHeaders,
    );
  }

  const parsed = contactSchema.safeParse(body);
  if (!parsed.success) {
    return json(
      {
        error: "That is not a message I recognise.",
        reason: "invalid_request",
        fields: parsed.error.issues.map((issue) => issue.path.join(".")),
      },
      400,
      limitHeaders,
    );
  }

  const requestId = newRequestId();
  if (parsed.data.website !== "") {
    return json({ accepted: true, requestId }, 202, limitHeaders);
  }

  const configured = mailConfiguration(env);
  if (!configured) {
    console.error(
      JSON.stringify({
        level: "error",
        event: "contact_delivery_failed",
        route: "/api/contact",
        requestId,
        reason: "not_configured",
      }),
    );
    return json(
      { accepted: false, reason: "unavailable", requestId },
      503,
      limitHeaders,
    );
  }

  try {
    const delivered = await fetchApi(RESEND_ENDPOINT, {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${configured.RESEND_API_KEY}`,
        "Content-Type": "application/json",
        "Idempotency-Key": `contact/${parsed.data.submissionId}`,
        "User-Agent":
          "FPLAndres/0.5 (+https://github.com/JamieMBright/fpl-andres)",
      },
      body: JSON.stringify({
        from: configured.CONTACT_FROM_EMAIL,
        to: [configured.CONTACT_TO_EMAIL],
        reply_to: parsed.data.email,
        subject: SUBJECT,
        text: parsed.data.message,
      }),
    });
    if (!delivered.ok) {
      console.error(
        JSON.stringify({
          level: "error",
          event: "contact_delivery_failed",
          route: "/api/contact",
          requestId,
          reason: "provider_refused",
          status: delivered.status,
        }),
      );
      return json(
        { accepted: false, reason: "unavailable", requestId },
        503,
        limitHeaders,
      );
    }
    return json({ accepted: true, requestId }, 202, limitHeaders);
  } catch {
    console.error(
      JSON.stringify({
        level: "error",
        event: "contact_delivery_failed",
        route: "/api/contact",
        requestId,
        reason: "provider_unreachable",
      }),
    );
    return json(
      { accepted: false, reason: "unavailable", requestId },
      503,
      limitHeaders,
    );
  }
}

/** Test seam: module state intentionally survives warm production requests. */
export function resetContactRateLimiter(): void {
  limiter.reset();
}
