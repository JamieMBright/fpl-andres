/**
 * Probe the deployed API and name what is wrong, from a browser.
 *
 * The dev server answers `/api/*` from a Vite plugin that imports the handler
 * libraries directly, so it never touches Vercel's filesystem router or its
 * bundler. A route can therefore be perfectly healthy locally and broken in
 * production, which has now happened three times. `test:deployed` catches it,
 * but that needs a terminal, and the person who notices the failure is usually
 * holding a phone.
 *
 * The classification below is the whole point. A 502 on the analysis tab has
 * four unrelated causes and the fix differs for each, so the page reports which
 * one it is rather than that something went wrong.
 */

export type ProbeVerdict =
  | "ok"
  | "not_routed"
  | "function_crashed"
  | "upstream_blocked"
  | "upstream_unreachable"
  | "rate_limited"
  | "refused"
  | "unexpected";

export interface ProbeTarget {
  /** Stable key, used by the page and by the workflow report. */
  id: string;
  path: string;
  label: string;
  /** What a healthy body looks like. Absent when any 2xx will do. */
  expect?: (body: string) => boolean;
}

export interface ProbeResult {
  id: string;
  label: string;
  path: string;
  verdict: ProbeVerdict;
  status: number | null;
  contentType: string | null;
  /** Vercel sets this on its own error pages; ours never carry it. */
  vercelError: string | null;
  /** Our correlation id, when the handler minted one. */
  requestId: string | null;
  /** The `reason` field our handlers put in a JSON error body. */
  reason: string | null;
  summary: string;
  durationMs: number;
}

/**
 * The exact calls the product makes, in the order the analysis tab makes them.
 *
 * `bootstrap-static` carries no trailing slash on purpose: Vercel's catch-all
 * route does not match a path that ends in one, so the browser asks without it
 * and the proxy restores it before validating against the allow-list.
 */
export const PROBE_TARGETS: ProbeTarget[] = [
  {
    id: "health",
    path: "/api/health",
    label: "Health",
  },
  {
    id: "bootstrap",
    path: "/api/fpl/bootstrap-static",
    label: "Player list (analysis tab)",
    expect: (body) => body.includes('"elements"'),
  },
  {
    id: "fixtures",
    path: "/api/fpl/fixtures",
    label: "Fixture list (analysis tab)",
    expect: (body) => body.trimStart().startsWith("["),
  },
  {
    id: "team",
    path: "/api/team/212279",
    label: "Team lookup",
    expect: (body) => /"status":"(ready|unavailable|degraded)"/.test(body),
  },
];

const BODY_SAMPLE_LIMIT = 400;

/**
 * Decide what a response means.
 *
 * Split from the fetch so it can be tested against every shape without a
 * network, and reused by the workflow report.
 */
export function classify(
  target: ProbeTarget,
  status: number,
  headers: { get(name: string): string | null },
  body: string,
): Pick<
  ProbeResult,
  "verdict" | "summary" | "reason" | "vercelError" | "requestId" | "contentType"
> {
  const contentType = headers.get("content-type");
  const vercelError = headers.get("x-vercel-error");
  const requestId = headers.get("x-fpl-andres-request-id");
  const reason = readReason(body);
  const isHtml = (contentType ?? "").includes("text/html");

  // Vercel's own failure, before our code ran or because it threw on load.
  // Our handlers answer 500 for nothing, so a bare 500 is always this.
  if (vercelError !== null || (status >= 500 && isHtml) || status === 500) {
    return {
      verdict: "function_crashed",
      contentType,
      vercelError,
      requestId,
      reason,
      summary:
        "The serverless function failed to run. This is a build or module-load problem, not FPL being down — check that every package the route imports emits JavaScript rather than TypeScript.",
    };
  }

  // The single-page rewrite answering means no function was matched.
  if (isHtml || status === 404) {
    return {
      verdict: "not_routed",
      contentType,
      vercelError,
      requestId,
      reason,
      summary:
        "The request fell through to the app shell, so no function is deployed at this path. Check the `functions` globs in vercel.json against the files under api/.",
    };
  }

  if (status === 429) {
    return {
      verdict: "rate_limited",
      contentType,
      vercelError,
      requestId,
      reason,
      summary: "Rate limited. Wait a minute and probe again.",
    };
  }

  if (reason === "unexpected_format") {
    return {
      verdict: "upstream_blocked",
      contentType,
      vercelError,
      requestId,
      reason,
      summary:
        "Our function reached FPL and FPL answered with something that is not JSON — almost always a bot-protection page served to the datacentre IP. This is the classic works-locally-fails-deployed cause: FPL serves your laptop and blocks Vercel.",
    };
  }

  if (reason === "unreachable") {
    return {
      verdict: "upstream_unreachable",
      contentType,
      vercelError,
      requestId,
      reason,
      summary:
        "Our function could not complete the FPL fetch inside its budget, or every attempt threw. Look for `upstream_exhausted` in the Vercel logs: a `failures` list of timeouts means the budget is too tight for a cold instance.",
    };
  }

  if (status >= 400) {
    return {
      verdict: "refused",
      contentType,
      vercelError,
      requestId,
      reason,
      summary: `The function ran and refused the request with ${String(status)}${
        reason ? ` (${reason})` : ""
      }.`,
    };
  }

  if (target.expect && !target.expect(body)) {
    return {
      verdict: "unexpected",
      contentType,
      vercelError,
      requestId,
      reason,
      summary:
        "The route answered 200 but the body is not the shape this route is supposed to return. Suspect an upstream contract change.",
    };
  }

  return {
    verdict: "ok",
    contentType,
    vercelError,
    requestId,
    reason,
    summary: "Healthy.",
  };
}

function readReason(body: string): string | null {
  const match = /"reason"\s*:\s*"([a-z_]+)"/.exec(body);
  return match?.[1] ?? null;
}

/**
 * Run one probe. Never throws: a probe that fails to report is worse than
 * useless, because it looks like a fault in whatever is being diagnosed.
 */
export async function probe(
  target: ProbeTarget,
  fetchApi: typeof fetch = fetch,
  now: () => number = () => performance.now(),
): Promise<ProbeResult> {
  const startedAt = now();
  try {
    const response = await fetchApi(target.path, {
      headers: { Accept: "application/json" },
      // A stale CDN copy would describe a deployment that no longer exists.
      cache: "no-store",
    });
    const body = (await response.text()).slice(0, BODY_SAMPLE_LIMIT);
    return {
      id: target.id,
      label: target.label,
      path: target.path,
      status: response.status,
      durationMs: Math.round(now() - startedAt),
      ...classify(target, response.status, response.headers, body),
    };
  } catch (error) {
    return {
      id: target.id,
      label: target.label,
      path: target.path,
      verdict: "upstream_unreachable",
      status: null,
      contentType: null,
      vercelError: null,
      requestId: null,
      reason: null,
      durationMs: Math.round(now() - startedAt),
      summary: `The request could not be made at all: ${
        error instanceof Error ? error.message : String(error)
      }. On a deployed site this usually means a network fault or a blocked request rather than a server fault.`,
    };
  }
}

export async function probeAll(
  fetchApi: typeof fetch = fetch,
  targets: ProbeTarget[] = PROBE_TARGETS,
): Promise<ProbeResult[]> {
  // Sequential on purpose: parallel probes share a rate-limit bucket and would
  // diagnose each other.
  const results: ProbeResult[] = [];
  for (const target of targets) {
    results.push(await probe(target, fetchApi));
  }
  return results;
}

/**
 * One sentence naming the most likely cause across all probes, so the page can
 * lead with a conclusion rather than a table.
 */
export function overallVerdict(results: ProbeResult[]): string {
  const broken = results.filter((result) => result.verdict !== "ok");
  if (broken.length === 0) {
    return "Every route is healthy. If the analysis tab still fails, the fault is intermittent — probe again while it is failing.";
  }
  const worst = broken[0];
  if (worst === undefined) return "";
  const names = broken.map((result) => result.label).join(", ");
  return `${String(broken.length)} of ${String(results.length)} routes are failing (${names}). ${worst.summary}`;
}
