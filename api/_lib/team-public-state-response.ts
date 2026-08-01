import { playerIdentitySchema } from "@fpl-andres/contracts";
import { z } from "zod";

import { createFplProxyResponse, FPL_PROXY_BUDGET_MS } from "./fpl-proxy.js";
import {
  logHandlerOutcome,
  logUpstreamOutcome,
  newRequestId,
} from "./request-log.js";
import { SourceCache, sourceTtlMs } from "./source-cache.js";
import {
  assembleTeamPublicState,
  TeamPublicStateContractError,
} from "./team-public-state.js";

const MAX_PUBLIC_ID = 4_294_967_295;

/**
 * The picks fetch is sequential, not parallel, so it needs its own budget.
 *
 * Audit item #88. The two opening fetches share a deadline correctly -- they run
 * concurrently, so neither consumes the other's wall clock. Picks is different:
 * it cannot start until the entry response has named the current event, and it
 * was given whatever remained of the same deadline. A pair that took eight of
 * the eight and a half seconds left picks a quarter second, and the whole
 * request degraded on the one fetch that had done nothing wrong.
 */
const PICKS_BUDGET_MS = FPL_PROXY_BUDGET_MS;

type Sleep = (milliseconds: number) => Promise<void>;

interface TeamPublicStateDependencies {
  fetchUpstream?: typeof fetch;
  sleep?: Sleep;
  random?: () => number;
  now?: () => number;
  /** Test seam: a cache that outlived a test would answer the next one. */
  cache?: SourceCache<FetchSourceOutcome>;
}

interface FetchedSource {
  body: Uint8Array;
  fetchedAt: string;
  status: number;
}

type FetchSourceOutcome =
  | { kind: "ok"; source: FetchedSource }
  | { kind: "unreachable" }
  | { kind: "source_failed" };

/**
 * Module scope, so it survives between invocations of a warm instance. That is
 * the only place a per-instance cache can do any good.
 */
const defaultCache = new SourceCache<FetchSourceOutcome>();

/**
 * Test seam. A warm instance reusing bootstrap between two managers is the
 * intended behaviour; a test file reusing it between two cases is not, because
 * each case wants to describe a different upstream.
 */
export function resetSourceCache(): void {
  defaultCache.clear();
}

const entrySummarySchema = z
  .object({
    id: z.int().min(1).max(MAX_PUBLIC_ID),
    current_event: z.int().min(1).max(38).nullable(),
  })
  .passthrough();

const bootstrapSchema = z
  .object({
    events: z.array(
      z
        .object({
          id: z.int().min(1).max(38),
          deadline_time: z.iso.datetime(),
        })
        .passthrough(),
    ),
    elements: z.array(
      z
        .object({
          id: z.int().positive(),
          web_name: z.string().min(1),
          code: z.int().positive(),
          element_type: z.int().min(1).max(5),
          team: z.int().positive(),
          now_cost: z.int().positive(),
        })
        .passthrough(),
    ),
    element_types: z.array(
      z
        .object({
          id: z.int().min(1).max(5),
          singular_name_short: z.string().min(1),
        })
        .passthrough(),
    ),
    teams: z.array(
      z
        .object({
          id: z.int().positive(),
          short_name: z.string().min(1),
        })
        .passthrough(),
    ),
  })
  .passthrough();

/**
 * One request's timing and outcome, filled in as the handler proceeds.
 *
 * A mutable record rather than a return value because the builder below has a
 * dozen early returns, and threading a tuple through every one of them would
 * make the refusals harder to read than the work.
 */
interface RequestTrace {
  requestId: string;
  startedAt: number;
  upstreamMs: number;
  reason: string | null;
}

export async function createTeamPublicStateResponse(
  entryId: number,
  method: string,
  dependencies: TeamPublicStateDependencies = {},
): Promise<Response> {
  const now = dependencies.now ?? Date.now;
  const trace: RequestTrace = {
    requestId: newRequestId(),
    startedAt: now(),
    upstreamMs: 0,
    reason: null,
  };
  const response = await buildTeamPublicStateResponse(
    entryId,
    method,
    dependencies,
    trace,
  );
  logHandlerOutcome({
    requestId: trace.requestId,
    route: "/api/team/:id",
    status: response.status,
    reason: trace.reason,
    totalMs: now() - trace.startedAt,
    upstreamMs: trace.upstreamMs,
  });
  return response;
}

async function buildTeamPublicStateResponse(
  entryId: number,
  method: string,
  dependencies: TeamPublicStateDependencies,
  trace: RequestTrace,
): Promise<Response> {
  const fetchUpstream = dependencies.fetchUpstream ?? fetch;
  const sleep = dependencies.sleep ?? defaultSleep;
  const random = dependencies.random ?? Math.random;
  const now = dependencies.now ?? Date.now;
  const cache = dependencies.cache ?? defaultCache;

  if (method !== "GET") {
    return jsonResponse({ error: "Only GET is supported." }, 405, {
      Allow: "GET",
    });
  }
  if (!Number.isInteger(entryId) || entryId < 1 || entryId > MAX_PUBLIC_ID) {
    return jsonResponse(
      { error: "Team ID is outside the supported range." },
      400,
    );
  }

  const deadline = now() + FPL_PROXY_BUDGET_MS;
  const [entryOutcome, bootstrapOutcome] = await Promise.all([
    fetchSource(
      `/api/fpl/entry/${entryId}/`,
      "entry",
      fetchUpstream,
      sleep,
      random,
      now,
      deadline,
      trace,
      cache,
    ),
    fetchSource(
      "/api/fpl/bootstrap-static/",
      "bootstrap",
      fetchUpstream,
      sleep,
      random,
      now,
      deadline,
      trace,
      cache,
    ),
  ]);
  const preliminaryOutcome = worstOutcome(entryOutcome, bootstrapOutcome);
  if (preliminaryOutcome) {
    return degradedResponse(preliminaryOutcome, trace);
  }
  if (entryOutcome.kind !== "ok" || bootstrapOutcome.kind !== "ok") {
    return degradedResponse("fpl_source_failed", trace);
  }
  const entrySource = entryOutcome.source;
  const bootstrapSource = bootstrapOutcome.source;
  if (entrySource.status === 404) {
    return unavailableResponse("entry_unavailable", trace);
  }
  if (!isSuccessful(entrySource) || !isSuccessful(bootstrapSource)) {
    return degradedResponse("fpl_source_failed", trace);
  }

  let entry: z.infer<typeof entrySummarySchema>;
  let bootstrap: z.infer<typeof bootstrapSchema>;
  try {
    entry = parseSource(entrySource, entrySummarySchema);
    bootstrap = parseSource(bootstrapSource, bootstrapSchema);
  } catch (error) {
    return contractFailure(error, trace, {
      entry: entrySource.status,
      bootstrap: bootstrapSource.status,
    });
  }
  if (entry.id !== entryId) {
    return contractFailure(
      new TeamPublicStateContractError("entry id does not match the request"),
      trace,
      { entry: entrySource.status, bootstrap: bootstrapSource.status },
    );
  }
  if (entry.current_event === null) {
    return unavailableResponse("no_processed_event", trace);
  }
  const event = bootstrap.events.find(({ id }) => id === entry.current_event);
  if (!event) {
    return contractFailure(
      new TeamPublicStateContractError(
        "bootstrap does not describe the current event",
      ),
      trace,
      { entry: entrySource.status, bootstrap: bootstrapSource.status },
    );
  }

  const picksOutcome = await fetchSource(
    `/api/fpl/entry/${entryId}/event/${entry.current_event}/picks/`,
    "picks",
    fetchUpstream,
    sleep,
    random,
    now,
    // Its own budget (#88): picks cannot start until entry has named the event,
    // so it must not inherit what the opening pair left behind.
    now() + PICKS_BUDGET_MS,
    trace,
    cache,
  );
  if (picksOutcome.kind !== "ok") {
    return degradedResponse(
      picksOutcome.kind === "unreachable"
        ? "fpl_unreachable"
        : "fpl_source_failed",
      trace,
    );
  }
  const picksSource = picksOutcome.source;
  if (picksSource.status === 404) {
    trace.reason = "picks_unavailable";
    return jsonResponse({
      status: "unavailable",
      reason: "picks_unavailable",
      event: entry.current_event,
    });
  }
  if (!isSuccessful(picksSource)) {
    return degradedResponse("fpl_source_failed", trace);
  }

  try {
    const positionCodes = new Map(
      bootstrap.element_types.map((type) => [
        type.id,
        type.singular_name_short,
      ]),
    );
    const teamShortNames = new Map(
      bootstrap.teams.map((team) => [team.id, team.short_name]),
    );
    const identities = new Map(
      bootstrap.elements.flatMap((element) => {
        // Validated through the contract rather than cast: an unrecognised
        // position or missing club leaves the pick opaque rather than half-named.
        const candidate = playerIdentitySchema.safeParse({
          webName: element.web_name,
          positionCode: positionCodes.get(element.element_type),
          teamShortName: teamShortNames.get(element.team),
          priceTenths: element.now_cost,
          code: element.code,
        });
        return candidate.success
          ? ([[element.id, candidate.data]] as const)
          : ([] as const);
      }),
    );

    const state = assembleTeamPublicState({
      entryBytes: entrySource.body,
      entryFetchedAt: entrySource.fetchedAt,
      picksBytes: picksSource.body,
      picksFetchedAt: picksSource.fetchedAt,
      stateSourceBytes: bootstrapSource.body,
      stateSourceFetchedAt: bootstrapSource.fetchedAt,
      stateAsOf: event.deadline_time,
      identities,
    });
    return jsonResponse({ status: "ready", state });
  } catch (error) {
    if (
      error instanceof TeamPublicStateContractError ||
      error instanceof z.ZodError
    ) {
      return contractFailure(error, trace, {
        entry: entrySource.status,
        bootstrap: bootstrapSource.status,
        picks: picksSource.status,
      });
    }
    throw error;
  }
}

/**
 * Record what upstream said before refusing.
 *
 * Audit item #92. This branch used to swallow the error and answer
 * `source_contract_failed`, which says an FPL payload changed shape but not
 * which one, nor what status it arrived with. A 200 that fails the contract is
 * a schema change; a 403 that fails it is a block page that got past the
 * content-type check. They need different responses from us and were
 * indistinguishable in the log.
 *
 * The exception message is recorded because it is ours -- every
 * TeamPublicStateContractError message is a fixed string naming a field, and a
 * ZodError issue path is a field name, not a value. Bodies never appear.
 */
function contractFailure(
  error: unknown,
  trace: RequestTrace,
  statuses: Record<string, number>,
): Response {
  console.warn(
    JSON.stringify({
      level: "warn",
      event: "source_contract_failed",
      requestId: trace.requestId,
      route: "/api/team/:id",
      upstreamStatuses: statuses,
      detail:
        error instanceof z.ZodError
          ? error.issues
              .slice(0, 5)
              .map((issue) => `${issue.path.join(".")}: ${issue.code}`)
          : error instanceof Error
            ? error.message
            : "unknown",
    }),
  );
  return degradedResponse("source_contract_failed", trace);
}

async function fetchSource(
  requestUrl: string,
  source: string,
  fetchUpstream: typeof fetch,
  sleep: Sleep,
  random: () => number,
  now: () => number,
  deadline: number,
  trace: RequestTrace,
  cache: SourceCache<FetchSourceOutcome>,
): Promise<FetchSourceOutcome> {
  const startedAt = now();
  // Keyed by the request URL rather than by the source name: two managers'
  // picks are different requests and must never share an entry.
  const { value: outcome, reused } = await cache.resolve(
    requestUrl,
    sourceTtlMs(source),
    () => readSource(requestUrl, fetchUpstream, sleep, random, now, deadline),
    // A failed read resolves with a failure outcome rather than rejecting, so
    // the cache has to be told. Holding one would serve the outage for a
    // minute after upstream recovered.
    (candidate) => candidate.kind === "ok" && isSuccessful(candidate.source),
  );
  // Concurrent sources overlap, so this sums to more than the wall clock. That
  // is the intended reading: it is time spent waiting on FPL, not elapsed time.
  trace.upstreamMs += now() - startedAt;
  logUpstreamOutcome({
    requestId: trace.requestId,
    route: "/api/team/:id",
    source,
    status: outcome.kind === "ok" ? outcome.source.status : null,
    reason: outcome.kind === "ok" ? null : outcome.kind,
    durationMs: now() - startedAt,
    // Without this, a cache hit counts as a successful fetch and inflates the
    // success ratio the upstream-failure alert is measured against.
    reused,
  });
  return outcome;
}

async function readSource(
  requestUrl: string,
  fetchUpstream: typeof fetch,
  sleep: Sleep,
  random: () => number,
  now: () => number,
  deadline: number,
): Promise<FetchSourceOutcome> {
  const response = await createFplProxyResponse(
    requestUrl,
    "GET",
    fetchUpstream,
    sleep,
    random,
    now,
    deadline,
  );
  if (response.status === 502) {
    const parsed = await response
      .clone()
      .json()
      .catch(() => null);
    const reason =
      parsed && typeof parsed.reason === "string" ? parsed.reason : null;
    if (reason === "unexpected_format" || reason === "oversize") {
      return { kind: "source_failed" };
    }
    return { kind: "unreachable" };
  }
  return {
    kind: "ok",
    source: {
      body: new Uint8Array(await response.arrayBuffer()),
      fetchedAt: new Date(now()).toISOString(),
      status: response.status,
    },
  };
}

function worstOutcome(
  ...outcomes: FetchSourceOutcome[]
): "fpl_source_failed" | "fpl_unreachable" | null {
  if (outcomes.some((outcome) => outcome.kind === "source_failed")) {
    return "fpl_source_failed";
  }
  if (outcomes.some((outcome) => outcome.kind === "unreachable")) {
    return "fpl_unreachable";
  }
  return null;
}

function parseSource<Schema extends z.ZodType>(
  source: FetchedSource,
  schema: Schema,
): z.infer<Schema> {
  return schema.parse(
    JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(source.body)),
  );
}

function isSuccessful(source: FetchedSource): boolean {
  return source.status >= 200 && source.status < 300;
}

function degradedResponse(reason: string, trace: RequestTrace): Response {
  trace.reason = reason;
  return jsonResponse({ status: "degraded", reason }, 503);
}

function unavailableResponse(reason: string, trace: RequestTrace): Response {
  trace.reason = reason;
  return jsonResponse({ status: "unavailable", reason });
}

function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "private, no-store", ...headers },
  });
}

function defaultSleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
