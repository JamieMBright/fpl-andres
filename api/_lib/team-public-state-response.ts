import { z } from "zod";

import { createFplProxyResponse, FPL_PROXY_BUDGET_MS } from "./fpl-proxy.js";
import {
  assembleTeamPublicState,
  TeamPublicStateContractError,
} from "./team-public-state.js";

const MAX_PUBLIC_ID = 4_294_967_295;

type Sleep = (milliseconds: number) => Promise<void>;

interface TeamPublicStateDependencies {
  fetchUpstream?: typeof fetch;
  sleep?: Sleep;
  random?: () => number;
  now?: () => number;
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
  })
  .passthrough();

export async function createTeamPublicStateResponse(
  entryId: number,
  method: string,
  dependencies: TeamPublicStateDependencies = {},
): Promise<Response> {
  const fetchUpstream = dependencies.fetchUpstream ?? fetch;
  const sleep = dependencies.sleep ?? defaultSleep;
  const random = dependencies.random ?? Math.random;
  const now = dependencies.now ?? Date.now;

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
      fetchUpstream,
      sleep,
      random,
      now,
      deadline,
    ),
    fetchSource(
      "/api/fpl/bootstrap-static/",
      fetchUpstream,
      sleep,
      random,
      now,
      deadline,
    ),
  ]);
  const preliminaryOutcome = worstOutcome(entryOutcome, bootstrapOutcome);
  if (preliminaryOutcome) {
    return degradedResponse(preliminaryOutcome);
  }
  if (entryOutcome.kind !== "ok" || bootstrapOutcome.kind !== "ok") {
    return degradedResponse("fpl_source_failed");
  }
  const entrySource = entryOutcome.source;
  const bootstrapSource = bootstrapOutcome.source;
  if (entrySource.status === 404) {
    return jsonResponse({ status: "unavailable", reason: "entry_unavailable" });
  }
  if (!isSuccessful(entrySource) || !isSuccessful(bootstrapSource)) {
    return degradedResponse("fpl_source_failed");
  }

  let entry: z.infer<typeof entrySummarySchema>;
  let bootstrap: z.infer<typeof bootstrapSchema>;
  try {
    entry = parseSource(entrySource, entrySummarySchema);
    bootstrap = parseSource(bootstrapSource, bootstrapSchema);
  } catch {
    return degradedResponse("source_contract_failed");
  }
  if (entry.id !== entryId) {
    return degradedResponse("source_contract_failed");
  }
  if (entry.current_event === null) {
    return jsonResponse({
      status: "unavailable",
      reason: "no_processed_event",
    });
  }
  const event = bootstrap.events.find(({ id }) => id === entry.current_event);
  if (!event) {
    return degradedResponse("source_contract_failed");
  }

  const picksOutcome = await fetchSource(
    `/api/fpl/entry/${entryId}/event/${entry.current_event}/picks/`,
    fetchUpstream,
    sleep,
    random,
    now,
    deadline,
  );
  if (picksOutcome.kind !== "ok") {
    return degradedResponse(
      picksOutcome.kind === "unreachable"
        ? "fpl_unreachable"
        : "fpl_source_failed",
    );
  }
  const picksSource = picksOutcome.source;
  if (picksSource.status === 404) {
    return jsonResponse({
      status: "unavailable",
      reason: "picks_unavailable",
      event: entry.current_event,
    });
  }
  if (!isSuccessful(picksSource)) {
    return degradedResponse("fpl_source_failed");
  }

  try {
    const state = assembleTeamPublicState({
      entryBytes: entrySource.body,
      entryFetchedAt: entrySource.fetchedAt,
      picksBytes: picksSource.body,
      picksFetchedAt: picksSource.fetchedAt,
      stateSourceBytes: bootstrapSource.body,
      stateSourceFetchedAt: bootstrapSource.fetchedAt,
      stateAsOf: event.deadline_time,
    });
    return jsonResponse({ status: "ready", state });
  } catch (error) {
    if (
      error instanceof TeamPublicStateContractError ||
      error instanceof z.ZodError
    ) {
      return degradedResponse("source_contract_failed");
    }
    throw error;
  }
}

async function fetchSource(
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

function degradedResponse(reason: string): Response {
  return jsonResponse({ status: "degraded", reason }, 503);
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
