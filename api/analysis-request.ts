import type { VercelRequest, VercelResponse } from "@vercel/node";
import { z } from "zod";

import {
  clientAddress,
  rateLimitHeaders,
  RateLimiter,
  TEAM_STATE_POLICY,
} from "./_lib/rate-limit.js";
import {
  applyFailureHeaders,
  logHandlerFailure,
  logRateLimit,
  newRequestId,
} from "./_lib/request-log.js";
import {
  insertRow,
  readCredentials,
  SupabaseNotConfigured,
} from "./_lib/supabase-write.js";

/**
 * Record a transfer declaration for short-lived operational diagnostics.
 *
 * Two things the site cannot learn by reading what FPL publishes. A manager's
 * picks for the coming gameweek are private until the deadline, so between a
 * transfer and the deadline the public API still shows the old squad — and a
 * plan built from it recommends a transfer already made.
 *
 * Write-only on purpose. The plan is solved in the browser from the manager's
 * own `localStorage`, so nothing here is ever read back into a recommendation.
 * That matters because a Team ID is public and enumerable: if a declared
 * transfer fed the solve, anyone could poison anyone's plan by knowing their
 * number. As it stands the worst a forged row can do is make the owner's own
 * diagnostics wrong. A scheduled job deletes the row seven days after its
 * deadline, with a thirty-day absolute backstop.
 */

const requestSchema = z.object({
  season: z
    .string()
    .trim()
    .regex(/^\d{4}-\d{2}$/),
  entryId: z.int().min(1).max(4_294_967_295),
  event: z.int().min(1).max(47),
  transfer: z
    .object({
      elementOut: z.int().positive(),
      elementIn: z.int().positive(),
      pointsCharged: z.int().min(0).max(60).default(0),
    })
    .nullable()
    .default(null),
});

const limiter = new RateLimiter(TEAM_STATE_POLICY);
const MAX_BODY_BYTES = 4 * 1024;

function firstHeader(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function isJsonMediaType(value: string | undefined): boolean {
  return value?.split(";", 1)[0]?.trim().toLowerCase() === "application/json";
}

function hasAllowedOrigin(headers: VercelRequest["headers"]): boolean {
  const origin = firstHeader(headers.origin);
  if (origin === undefined) return false;

  const host = firstHeader(headers["x-forwarded-host"]);
  const protocol = firstHeader(headers["x-forwarded-proto"]);
  if (!host || !protocol) return false;
  try {
    return new URL(origin).origin === `${protocol}://${host}`;
  } catch {
    return false;
  }
}

export default async function analysisRequestHandler(
  request: VercelRequest,
  response: VercelResponse,
): Promise<void> {
  const startedAt = performance.now();
  response.setHeader("Cache-Control", "no-store");

  if (request.method !== "POST") {
    response.setHeader("Allow", "POST");
    response.status(405).json({ error: "Use POST.", reason: "method" });
    return;
  }

  if (!isJsonMediaType(firstHeader(request.headers["content-type"]))) {
    response.status(415).json({
      error: "Send a JSON request.",
      reason: "unsupported_media_type",
    });
    return;
  }

  const rawLength = firstHeader(request.headers["content-length"]);
  if (rawLength === undefined) {
    response.status(411).json({
      error: "Content-Length is required.",
      reason: "length_required",
    });
    return;
  }
  const declaredLength = Number(rawLength);
  if (!Number.isInteger(declaredLength) || declaredLength < 0) {
    response.status(400).json({
      error: "Content-Length is invalid.",
      reason: "invalid_content_length",
    });
    return;
  }
  if (declaredLength > MAX_BODY_BYTES) {
    response.status(413).json({
      error: "The request is too large.",
      reason: "payload_too_large",
    });
    return;
  }

  if (!hasAllowedOrigin(request.headers)) {
    response.status(403).json({
      error: "That origin is not allowed.",
      reason: "origin",
    });
    return;
  }

  let measuredLength: number;
  try {
    measuredLength = Buffer.byteLength(JSON.stringify(request.body));
  } catch {
    response.status(400).json({
      error: "That request cannot be read.",
      reason: "invalid_request",
    });
    return;
  }
  if (measuredLength > MAX_BODY_BYTES) {
    response.status(413).json({
      error: "The request is too large.",
      reason: "payload_too_large",
    });
    return;
  }

  const decision = limiter.check(clientAddress(request.headers));
  for (const [name, value] of Object.entries(
    rateLimitHeaders(TEAM_STATE_POLICY, decision),
  )) {
    response.setHeader(name, String(value));
  }
  if (!decision.allowed) {
    logRateLimit({ route: "/api/analysis-request", scope: decision.scope });
    response
      .status(429)
      .json({ error: "Too many requests.", reason: "rate_limited" });
    return;
  }

  const parsed = requestSchema.safeParse(request.body);
  if (!parsed.success) {
    // The field paths, never the values: the body carries a manager's squad.
    response.status(400).json({
      error: "That is not a request I recognise.",
      reason: "invalid_request",
      fields: parsed.error.issues.map((issue) => issue.path.join(".")),
    });
    return;
  }

  const { season, entryId, event, transfer } = parsed.data;
  try {
    const credentials = readCredentials();
    await insertRow(
      "analysis_requests",
      { season, entry_id: entryId, event },
      credentials,
    );
    if (transfer) {
      await insertRow(
        "declared_transfers",
        {
          season,
          entry_id: entryId,
          event,
          element_out: transfer.elementOut,
          element_in: transfer.elementIn,
          points_charged: transfer.pointsCharged,
        },
        credentials,
      );
    }
    response.status(202).json({ recorded: true });
  } catch (error) {
    const requestId = newRequestId();
    logHandlerFailure(requestId, {
      route: "/api/analysis-request",
      error,
      status: 503,
      startedAt,
    });
    applyFailureHeaders(response, requestId);
    // Recording is not the feature. A manager still gets a plan whether or not
    // this landed, so the failure is reported without pretending it succeeded.
    response.status(error instanceof SupabaseNotConfigured ? 501 : 503).json({
      error: "The request was not recorded.",
      reason: "not_recorded",
      requestId,
    });
  }
}
