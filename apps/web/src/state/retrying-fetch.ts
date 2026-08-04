/**
 * A browser fetch that survives a transient failure.
 *
 * The analysis and player pages load through `/api/fpl/*`, which is a
 * serverless proxy in front of the Premier League's API. Two things there fail
 * intermittently and recover on their own: a cold instance whose upstream call
 * exhausts its budget, and the shared request budget answering 429 while
 * another tab is mid-load. Both surfaced as a dead page that a reader fixed by
 * hitting refresh until it worked -- which is a retry, performed by hand.
 *
 * So the retry lives here instead, on the same terms `team-analysis.ts`
 * already uses: bounded attempts, exponential backoff, and an abort treated as
 * the caller changing their mind rather than as something to retry. A
 * genuinely dead endpoint still fails fast enough to say so.
 *
 * Only idempotent GETs go through this. Retrying anything else would be a
 * second write.
 */

const MAX_ATTEMPTS = 3;
const RETRY_BASE_MS = 250;

/** Statuses the proxy itself emits when the failure is worth asking again. */
const RETRYABLE_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);

export interface RetryingFetchOptions {
  fetchApi?: typeof fetch;
  wait?: (milliseconds: number) => Promise<void>;
  attempts?: number;
}

export function retryingFetch(
  options: RetryingFetchOptions = {},
): typeof fetch {
  const fetchApi = options.fetchApi ?? fetch;
  const wait =
    options.wait ??
    ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const attempts = options.attempts ?? MAX_ATTEMPTS;

  return async function fetchWithRetries(input, init) {
    let lastError: unknown = null;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const response = await fetchApi(input, init);
        if (
          !RETRYABLE_STATUSES.has(response.status) ||
          attempt === attempts - 1
        ) {
          return response;
        }
        // The body is never read on a retryable status, and an unread body
        // holds the connection open.
        await response.body?.cancel();
      } catch (error) {
        // An abort is the caller changing their mind, not a failure to retry.
        if (error instanceof DOMException && error.name === "AbortError") {
          throw error;
        }
        if (attempt === attempts - 1) throw error;
        lastError = error;
      }
      await wait(RETRY_BASE_MS * 2 ** attempt);
    }
    // Unreachable: the final attempt either returns or throws above. Kept
    // honest rather than asserted away.
    throw lastError instanceof Error
      ? lastError
      : new TypeError("Failed to fetch");
  };
}
