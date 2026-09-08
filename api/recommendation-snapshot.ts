import type { VercelRequest, VercelResponse } from "@vercel/node";
import { z } from "zod";

import seasonInputsData from "../apps/web/src/data/season-inputs.json" with { type: "json" };
import seasonPlanData from "../apps/web/src/data/season-plan.json" with { type: "json" };
import {
  requireArtifactVersion,
  SEASON_PLAN_SCHEMA_VERSION,
} from "../apps/web/src/state/artifact-version.js";
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
  readCredentials,
  readRows,
  SupabaseNotConfigured,
  upsertRow,
} from "./_lib/supabase-write.js";

type PlanArtifact = {
  schemaVersion: number;
  modelVersion: string;
  season: string;
  gameweeks: {
    event: number;
    deadline: string;
  }[];
};

type InputsArtifact = {
  players: { id: number; position: string }[];
};

const PLAN = seasonPlanData as unknown as PlanArtifact;
const INPUTS = seasonInputsData as unknown as InputsArtifact;
requireArtifactVersion("season-plan", PLAN, SEASON_PLAN_SCHEMA_VERSION);

const playerPositions = new Map(
  INPUTS.players.map((player) => [player.id, player.position]),
);
const validPlayerIds = new Set(playerPositions.keys());
const gameweeks = new Map(PLAN.gameweeks.map((week) => [week.event, week]));

const snapshotSchema = z
  .object({
    season: z.string().regex(/^\d{4}-\d{2}$/),
    entryId: z.int().min(1).max(4_294_967_295),
    event: z.int().min(1).max(47),
    deadline: z.iso.datetime(),
    modelVersion: z.string().min(1),
    starters: z.array(z.int().positive()).length(11),
    bench: z.array(z.int().positive()).length(4),
    captain: z.int().positive(),
    viceCaptain: z.int().positive(),
    transferIn: z.int().positive().nullable(),
    transferOut: z.int().positive().nullable(),
    chip: z.enum(["Free Hit", "Wildcard"]).nullable(),
    projectedPoints: z.number().finite(),
    netExpectedPoints: z.number().finite(),
    paidTransfers: z.int().min(0).max(47),
    transferCost: z.number().finite().min(0),
    confidence: z.enum(["firm", "projected", "provisional"]),
    recordedAt: z.iso.datetime(),
    sourceReference: z.string().min(1).max(500).nullable(),
  })
  .strict();

type Snapshot = z.infer<typeof snapshotSchema>;

const databaseRowSchema = z.object({
  season: z.string(),
  entry_id: z.number().int().positive(),
  event: z.number().int(),
  deadline: z.string(),
  model_version: z.string(),
  starters: z.array(z.number().int().positive()),
  bench: z.array(z.number().int().positive()),
  captain: z.number().int().positive(),
  vice_captain: z.number().int().positive(),
  transfer_in: z.number().int().positive().nullable(),
  transfer_out: z.number().int().positive().nullable(),
  chip: z.enum(["Free Hit", "Wildcard"]).nullable(),
  projected_points: z.number(),
  net_expected_points: z.number(),
  paid_transfers: z.number().int(),
  transfer_cost: z.number(),
  confidence: z.enum(["firm", "projected", "provisional"]),
  recorded_at: z.string(),
  source_reference: z.string().nullable(),
});

const limiter = new RateLimiter(TEAM_STATE_POLICY);
const MAX_BODY_BYTES = 4 * 1024;
const SAFE_COLUMNS = [
  "season",
  "entry_id",
  "event",
  "deadline",
  "model_version",
  "starters",
  "bench",
  "captain",
  "vice_captain",
  "transfer_in",
  "transfer_out",
  "chip",
  "projected_points",
  "net_expected_points",
  "paid_transfers",
  "transfer_cost",
  "confidence",
  "recorded_at",
  "source_reference",
].join(",");

function firstHeader(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function isJsonMediaType(value: string | undefined): boolean {
  return value?.split(";", 1)[0]?.trim().toLowerCase() === "application/json";
}

function hasAllowedOrigin(headers: VercelRequest["headers"]): boolean {
  const origin = firstHeader(headers.origin);
  const host = firstHeader(headers["x-forwarded-host"]);
  const protocol = firstHeader(headers["x-forwarded-proto"]);
  if (!origin || !host || !protocol) return false;
  try {
    return new URL(origin).origin === `${protocol}://${host}`;
  } catch {
    return false;
  }
}

function issueFields(error: z.ZodError): string[] {
  return error.issues.map((issue) => issue.path.join("."));
}

function validateCanonical(snapshot: Snapshot): z.ZodError | null {
  const week = gameweeks.get(snapshot.event);
  const fields: { path: (string | number)[]; message: string }[] = [];
  if (snapshot.season !== PLAN.season) {
    fields.push({ path: ["season"], message: "season is not current" });
  }
  if (!week) {
    fields.push({
      path: ["event"],
      message: "event is not in the canonical plan",
    });
  } else {
    if (Date.parse(snapshot.deadline) !== Date.parse(week.deadline)) {
      fields.push({
        path: ["deadline"],
        message: "deadline does not match event",
      });
    }
  }
  if (snapshot.modelVersion !== PLAN.modelVersion) {
    fields.push({ path: ["modelVersion"], message: "model version is stale" });
  }
  const squad = [...snapshot.starters, ...snapshot.bench];
  const ids = [...new Set(squad)];
  for (const id of ids) {
    if (!validPlayerIds.has(id))
      fields.push({ path: ["starters"], message: "unknown player id" });
  }
  if (new Set(squad).size !== squad.length) {
    fields.push({
      path: ["starters"],
      message: "squad players must be unique",
    });
  }
  if (!snapshot.starters.includes(snapshot.captain)) {
    fields.push({ path: ["captain"], message: "captain must start" });
  }
  if (!snapshot.starters.includes(snapshot.viceCaptain)) {
    fields.push({ path: ["viceCaptain"], message: "vice-captain must start" });
  }
  if (snapshot.captain === snapshot.viceCaptain) {
    fields.push({
      path: ["viceCaptain"],
      message: "captain and vice-captain must differ",
    });
  }
  if ((snapshot.transferIn === null) !== (snapshot.transferOut === null)) {
    fields.push({ path: ["transferIn"], message: "transfers must be a pair" });
  }
  for (const id of [snapshot.transferIn, snapshot.transferOut]) {
    if (id !== null && !validPlayerIds.has(id)) {
      fields.push({
        path: ["transferIn"],
        message: "unknown transfer player id",
      });
    }
  }
  const shape = { GKP: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const id of squad) {
    const position = playerPositions.get(id);
    if (position === undefined) continue;
    if (position in shape) shape[position as keyof typeof shape] += 1;
  }
  for (const [position, expected] of Object.entries({
    GKP: 2,
    DEF: 5,
    MID: 5,
    FWD: 3,
  })) {
    if (shape[position as keyof typeof shape] !== expected) {
      fields.push({
        path: ["starters"],
        message: `squad must contain ${expected} ${position}`,
      });
    }
  }
  return fields.length === 0
    ? null
    : new z.ZodError(fields.map((field) => ({ code: "custom", ...field })));
}

function toDatabaseRow(snapshot: Snapshot): Record<string, unknown> {
  return {
    season: snapshot.season,
    entry_id: snapshot.entryId,
    event: snapshot.event,
    deadline: snapshot.deadline,
    model_version: snapshot.modelVersion,
    starters: snapshot.starters,
    bench: snapshot.bench,
    captain: snapshot.captain,
    vice_captain: snapshot.viceCaptain,
    transfer_in: snapshot.transferIn,
    transfer_out: snapshot.transferOut,
    chip: snapshot.chip,
    projected_points: snapshot.projectedPoints,
    net_expected_points: snapshot.netExpectedPoints,
    paid_transfers: snapshot.paidTransfers,
    transfer_cost: snapshot.transferCost,
    confidence: snapshot.confidence,
    recorded_at: snapshot.recordedAt,
    source_reference: snapshot.sourceReference,
  };
}

function fromDatabaseRow(row: unknown): Snapshot | null {
  const parsed = databaseRowSchema.safeParse(row);
  if (!parsed.success) return null;
  const value = parsed.data;
  const snapshot = {
    season: value.season,
    entryId: value.entry_id,
    event: value.event,
    deadline: value.deadline,
    modelVersion: value.model_version,
    starters: value.starters,
    bench: value.bench,
    captain: value.captain,
    viceCaptain: value.vice_captain,
    transferIn: value.transfer_in,
    transferOut: value.transfer_out,
    chip: value.chip,
    projectedPoints: value.projected_points,
    netExpectedPoints: value.net_expected_points,
    paidTransfers: value.paid_transfers,
    transferCost: value.transfer_cost,
    confidence: value.confidence,
    recordedAt: value.recorded_at,
    sourceReference: value.source_reference,
  };
  return snapshotSchema.safeParse(snapshot).success ? snapshot : null;
}

export default async function recommendationSnapshotHandler(
  request: VercelRequest,
  response: VercelResponse,
): Promise<void> {
  response.setHeader("Cache-Control", "no-store");
  const startedAt = performance.now();
  const decision = limiter.check(clientAddress(request.headers));
  for (const [name, value] of Object.entries(
    rateLimitHeaders(TEAM_STATE_POLICY, decision),
  )) {
    response.setHeader(name, String(value));
  }
  if (!decision.allowed) {
    logRateLimit({
      route: "/api/recommendation-snapshot",
      scope: decision.scope,
    });
    response
      .status(429)
      .json({ error: "Too many requests.", reason: "rate_limited" });
    return;
  }

  if (request.method === "GET") {
    const rawEntryId = request.query?.entryId;
    const entryId =
      typeof rawEntryId === "string" && /^\d+$/.test(rawEntryId)
        ? Number(rawEntryId)
        : 0;
    if (
      !Number.isSafeInteger(entryId) ||
      entryId < 1 ||
      entryId > 4_294_967_295
    ) {
      response
        .status(400)
        .json({ error: "That is not a Team ID.", reason: "invalid_entry_id" });
      return;
    }
    try {
      const credentials = readCredentials();
      const query = new URLSearchParams({
        select: SAFE_COLUMNS,
        entry_id: `eq.${String(entryId)}`,
        limit: "1",
      });
      const rows = await readRows(
        "recommendation_snapshots_latest",
        query,
        credentials,
      );
      const snapshot = fromDatabaseRow(rows[0]);
      if (rows.length > 0 && snapshot === null)
        throw new Error("invalid recommendation snapshot row");
      response.status(200).json({ snapshot });
    } catch (error) {
      const requestId = newRequestId();
      logHandlerFailure(requestId, {
        route: "/api/recommendation-snapshot",
        error,
        status: 503,
        startedAt,
      });
      applyFailureHeaders(response, requestId);
      response.status(error instanceof SupabaseNotConfigured ? 501 : 503).json({
        error: "The recommendation was not available.",
        reason: "not_available",
        requestId,
      });
    }
    return;
  }

  if (request.method !== "POST") {
    response.setHeader("Allow", "GET, POST");
    response.status(405).json({ error: "Use GET or POST.", reason: "method" });
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
  const declaredLength = rawLength === undefined ? NaN : Number(rawLength);
  if (rawLength === undefined) {
    response.status(411).json({
      error: "Content-Length is required.",
      reason: "length_required",
    });
    return;
  }
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
    response
      .status(403)
      .json({ error: "That origin is not allowed.", reason: "origin" });
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
  const parsed = snapshotSchema.safeParse(request.body);
  if (!parsed.success) {
    response.status(400).json({
      error: "That recommendation is not valid.",
      reason: "invalid_request",
      fields: issueFields(parsed.error),
    });
    return;
  }
  const canonicalError = validateCanonical(parsed.data);
  if (canonicalError) {
    response.status(400).json({
      error: "That recommendation is not valid.",
      reason: "invalid_request",
      fields: issueFields(canonicalError),
    });
    return;
  }
  try {
    const credentials = readCredentials();
    await upsertRow(
      "recommendation_snapshots",
      toDatabaseRow(parsed.data),
      ["entry_id", "event"],
      credentials,
    );
    response.status(202).json({ recorded: true });
  } catch (error) {
    const requestId = newRequestId();
    logHandlerFailure(requestId, {
      route: "/api/recommendation-snapshot",
      error,
      status: 503,
      startedAt,
    });
    applyFailureHeaders(response, requestId);
    response.status(error instanceof SupabaseNotConfigured ? 501 : 503).json({
      error: "The recommendation was not recorded.",
      reason: "not_recorded",
      requestId,
    });
  }
}
