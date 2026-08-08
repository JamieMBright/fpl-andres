/**
 * What the proxy said, read back verbatim.
 *
 * `api/_lib/fpl-proxy.ts` already classifies a failed upstream fetch and puts
 * the upstream status, the media type and a plain sentence in the body. The
 * browser was discarding all of that and printing "I could not reach FPL",
 * which is true of a timeout and false of a 403. A refusal, a rate limit, a bot
 * challenge and an outage need four different things from the reader, and only
 * one of them is worth retrying.
 */

/** The reasons the proxy emits. Mirrors `FplProxyErrorReason`. */
const REFUSAL_REASONS = [
  "unreachable",
  "unexpected_format",
  "oversize",
  "challenged",
  "refused",
  "rate_limited",
  "upstream_down",
] as const;

export type ProxyRefusalReason = (typeof REFUSAL_REASONS)[number];

export interface ProxyRefusal {
  /** Discriminant: a profile is an object too, and both share a slot. */
  readonly kind: "refusal";
  /** The proxy's own sentence, including the upstream status. */
  readonly said: string;
  readonly reason: ProxyRefusalReason;
}

function isRefusalReason(value: unknown): value is ProxyRefusalReason {
  return REFUSAL_REASONS.some((reason) => reason === value);
}

/**
 * A refusal shares a slot with a manager profile, which is also an object.
 * `profile.kind === "refusal"` cannot narrow that union on its own, because
 * `ManagerProfile` has no `kind` at all.
 */
export function isProxyRefusal(value: unknown): value is ProxyRefusal {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { kind?: unknown }).kind === "refusal"
  );
}

/**
 * Reads a proxy error body. Returns null for anything that is not one — an
 * empty body, an HTML error page, a response from something that is not this
 * proxy — so the caller falls back rather than inventing a diagnosis.
 */
export function readProxyRefusal(body: unknown): ProxyRefusal | null {
  if (typeof body !== "object" || body === null) return null;
  const record = body as Record<string, unknown>;
  const said = record["error"];
  const reason = record["reason"];
  if (typeof said !== "string" || said.length === 0) return null;
  if (!isRefusalReason(reason)) return null;
  return { kind: "refusal", said, reason };
}

/**
 * Whether waiting changes anything. Stated rather than implied, because "try
 * again" against a block trains the reader to distrust every retry button.
 */
export function refusalRecourse(reason: ProxyRefusalReason): string {
  switch (reason) {
    case "rate_limited":
      return "That is a limit, not a verdict: it should clear on its own, so this is worth trying again shortly.";
    case "refused":
    case "challenged":
      return "Retrying will not change it. FPL is turning away the machine this page is served from, not you — the same request works from a browser.";
    case "upstream_down":
      return "FPL's own API is not serving right now. Nothing here can fix that; it comes back when they do.";
    case "oversize":
    case "unexpected_format":
      return "FPL answered with something I will not parse rather than guess at. That one is mine to fix.";
    case "unreachable":
      return "Nothing answered inside the time I allow. Worth trying again.";
  }
}
