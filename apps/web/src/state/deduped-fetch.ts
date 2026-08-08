/**
 * Collapses concurrent identical GETs into one request.
 *
 * Two components mounting at once, or a StrictMode double
 * render in development, produce two identical requests for the same URL. The
 * second is pure waste: the responses are the same, and the proxy behind them
 * has a rate limit.
 *
 * Keyed on the URL only, which is correct here because every deduplicated call
 * is a GET with no body. It would be wrong the moment a POST used it, so the
 * signature refuses anything else.
 *
 * The entry is removed as soon as the promise settles, so this is a request
 * coalescer and not a cache. Caching responses would need an invalidation
 * story, and the data behind these URLs changes on a deadline.
 */

const inFlight = new Map<string, Promise<Response>>();

export function dedupedFetch(
  input: string,
  init: (RequestInit & { method?: "GET" }) | undefined,
  fetchApi: typeof fetch,
): Promise<Response> {
  // An abort signal makes the request caller-specific: sharing one promise
  // would let the first caller's abort cancel the second caller's request.
  if (init?.signal) {
    return fetchApi(input, init);
  }

  const existing = inFlight.get(input);
  if (existing) {
    // Clone, because a Response body can only be read once and both callers
    // will read it.
    return existing.then((response) => response.clone());
  }

  const pending = fetchApi(input, init);
  inFlight.set(input, pending);
  // Both branches handled explicitly. A `.finally()` here re-throws, producing
  // a rejected promise nobody awaits and an unhandled-rejection warning that
  // makes every failing-network test look like a broken test.
  pending.then(
    () => inFlight.delete(input),
    () => inFlight.delete(input),
  );
  return pending.then((response) => response.clone());
}

/** Test seam. Production code has no reason to call this. */
export function clearInFlight(): void {
  inFlight.clear();
}
