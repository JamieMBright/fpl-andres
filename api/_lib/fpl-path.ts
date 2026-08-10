const PROXY_PREFIX = "/api/fpl/";
const FPL_API_ORIGIN = "https://fantasy.premierleague.com/api/";
const MAX_PUBLIC_ID = 4_294_967_295;
const MAX_ELEMENT_ID = 2_000;
const MAX_EVENT_ID = 38;

type EndpointKind = "fixtures" | "standings" | "none";

export class FplPathError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FplPathError";
  }
}

export function normalizeVercelProxyUrl(requestUrl: string): string {
  const queryIndex = requestUrl.indexOf("?");
  if (queryIndex === -1) {
    return requestUrl;
  }

  const rawPath = requestUrl.slice(0, queryIndex);
  const parameters = new URLSearchParams(requestUrl.slice(queryIndex + 1));
  parameters.delete("path");
  parameters.delete("...path");
  const query = parameters.toString();
  return query ? `${rawPath}?${query}` : rawPath;
}

export function resolveFplUpstreamUrl(requestUrl: string): URL {
  const queryIndex = requestUrl.indexOf("?");
  const rawPath =
    queryIndex === -1 ? requestUrl : requestUrl.slice(0, queryIndex);
  const rawQuery = queryIndex === -1 ? "" : requestUrl.slice(queryIndex + 1);

  if (!rawPath.startsWith(PROXY_PREFIX)) {
    throw new FplPathError("request path is outside the FPL proxy");
  }

  const endpointPath = rawPath.slice(PROXY_PREFIX.length);
  rejectUnsafePath(rawPath, endpointPath);
  // Vercel's catch-all route does not match a request path ending in a slash:
  // `/api/fpl/bootstrap-static/` was answered 404 by the edge without the
  // function running at all. FPL's own endpoints require that slash, so the
  // browser asks without one and it is restored here. The allow-list still sees
  // exactly the anchored form it always did, so nothing new becomes reachable.
  const canonicalPath =
    endpointPath === "" || endpointPath.endsWith("/")
      ? endpointPath
      : `${endpointPath}/`;
  const endpointKind = validateEndpointPath(canonicalPath);
  const query = validateQuery(endpointKind, rawQuery);

  const upstreamUrl = new URL(`${canonicalPath}${query}`, FPL_API_ORIGIN);
  requireUnchangedByResolution(upstreamUrl, canonicalPath, query);
  return upstreamUrl;
}

/**
 * Refuse anything the URL parser did not leave exactly as the allow-list saw it.
 *
 * The allow-list matches a string; `fetch` sends a resolved URL.
 * Everywhere those two can differ is a place where a request is approved in one
 * form and issued in another: a dot segment collapsed, a percent-escape
 * decoded, a backslash treated as a separator, a `@` reinterpreted as userinfo
 * and the origin moved somewhere else entirely.
 *
 * `rejectUnsafePath` and the anchored patterns already close every variant we
 * know of, and the tests below try them. This closes the ones we do not: rather
 * than enumerate the tricks, compare the resolved URL against the only string
 * that could have been approved. If they differ at all, the request never
 * leaves.
 */
function requireUnchangedByResolution(
  upstreamUrl: URL,
  endpointPath: string,
  query: string,
): void {
  if (upstreamUrl.href !== `${FPL_API_ORIGIN}${endpointPath}${query}`) {
    throw new FplPathError(
      "request path changed under URL resolution and was not sent",
    );
  }
}

function rejectUnsafePath(rawPath: string, endpointPath: string): void {
  if (
    rawPath.includes("..") ||
    rawPath.includes("\\") ||
    endpointPath.includes("//") ||
    /%(?:2e|2f|5c)/i.test(rawPath)
  ) {
    throw new FplPathError("request path contains an unsafe segment");
  }
}

function validateEndpointPath(path: string): EndpointKind {
  if (path === "bootstrap-static/") {
    return "none";
  }
  if (path === "fixtures/") {
    return "fixtures";
  }
  if (/^entry\/[1-9]\d{0,9}\/$/.test(path)) {
    requireBoundedPathId(path, 1, MAX_PUBLIC_ID);
    return "none";
  }
  if (/^entry\/[1-9]\d{0,9}\/history\/$/.test(path)) {
    requireBoundedPathId(path, 1, MAX_PUBLIC_ID);
    return "none";
  }
  const picksMatch = /^entry\/([1-9]\d{0,9})\/event\/([1-9]\d?)\/picks\/$/.exec(
    path,
  );
  if (picksMatch) {
    requireIntegerInRange(picksMatch[1], "entry ID", 1, MAX_PUBLIC_ID);
    requireIntegerInRange(picksMatch[2], "event ID", 1, MAX_EVENT_ID);
    return "none";
  }
  // What every player actually did in a gameweek. The only public endpoint that
  // carries realised goals, assists, clean sheets, bonus and defensive
  // contributions per element, which is what a squad card needs to show a haul
  // rather than a number. It names no manager and takes no id.
  const liveMatch = /^event\/([1-9]\d?)\/live\/$/.exec(path);
  if (liveMatch) {
    requireIntegerInRange(liveMatch[1], "event ID", 1, MAX_EVENT_ID);
    return "none";
  }
  const elementMatch = /^element-summary\/([1-9]\d{0,3})\/$/.exec(path);
  if (elementMatch) {
    requireIntegerInRange(elementMatch[1], "element ID", 1, MAX_ELEMENT_ID);
    return "none";
  }
  const standingsMatch = /^leagues-classic\/([1-9]\d{0,9})\/standings\/$/.exec(
    path,
  );
  if (standingsMatch) {
    requireIntegerInRange(standingsMatch[1], "league ID", 1, MAX_PUBLIC_ID);
    return "standings";
  }

  throw new FplPathError("request path is not an allowlisted FPL endpoint");
}

function requireBoundedPathId(
  path: string,
  minimum: number,
  maximum: number,
): void {
  const identifier = path.split("/")[1];
  requireIntegerInRange(identifier, "entry ID", minimum, maximum);
}

function requireIntegerInRange(
  rawValue: string | undefined,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (!rawValue || !/^[1-9]\d*$/.test(rawValue)) {
    throw new FplPathError(`${label} must be a positive integer`);
  }
  const value = Number(rawValue);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new FplPathError(`${label} is outside the supported range`);
  }
  return value;
}

function validateQuery(kind: EndpointKind, rawQuery: string): string {
  if (!rawQuery) {
    return "";
  }
  if (kind === "none") {
    throw new FplPathError(
      "this FPL endpoint does not accept query parameters",
    );
  }

  const parameters = new URLSearchParams(rawQuery);
  const allowed =
    kind === "fixtures"
      ? new Map([["event", MAX_EVENT_ID]])
      : new Map([
          ["page_new_entries", 9_999],
          ["page_standings", 9_999],
          ["phase", 99],
        ]);
  const canonical = new URLSearchParams();

  for (const key of parameters.keys()) {
    const maximum = allowed.get(key);
    if (maximum === undefined) {
      throw new FplPathError(`query parameter '${key}' is not allowed`);
    }
    const values = parameters.getAll(key);
    if (values.length !== 1) {
      throw new FplPathError(`query parameter '${key}' must appear once`);
    }
  }

  for (const key of [...allowed.keys()].sort()) {
    const value = parameters.get(key);
    if (value !== null) {
      requireIntegerInRange(value, key, 1, allowed.get(key) ?? 1);
      canonical.set(key, value);
    }
  }

  const serialized = canonical.toString();
  return serialized ? `?${serialized}` : "";
}
