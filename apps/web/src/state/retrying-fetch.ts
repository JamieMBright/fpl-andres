import { dedupedFetch } from "./deduped-fetch";

/**
 * One bounded retry policy for the two tabs that read the FPL proxy.
 *
 * The analysis and players tabs were failing intermittently while a reload of
 * the same page succeeded, which is the signature of a transient upstream
 * rather than a broken build. Three things behind these two URLs are allowed to
 * fail occasionally and to succeed on the very next attempt: FPL itself under
 * load, a cold serverless instance that spends its budget starting rather than
 * fetching, and an ordinary dropped connection on a phone. In each case the
 * page had already given up and was asking the reader to hit refresh, which is
 * exactly what a retry does, only worse — it discards the rest of the page too.
 *
 * `refreshTeamAnalysis` has done this for the team route since it was written.
 * The numbers here are deliberately the same: three attempts, 250 ms doubling.
 *
 * Two things it will not do. It does not retry an abort, because that is the
 * caller changing their mind rather than a failure. It does not retry a status
 * the next attempt cannot improve — a 400 from the allow-list or a 404 from FPL
 * is an answer, and asking again only spends someone else's request budget.
 */

export const RETRY_BASE_MS = 250;
const MAX_ATTEMPTS = 3;

/**
 * Worth asking again. A 429 is our own limiter or FPL's and carries its own
 * backoff upstream; the rest are the proxy saying it could not finish in time.
 */
const RETRYABLE_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);

export type Wait = (milliseconds: number) => Promise<void>;

const defaultWait: Wait = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

export async function retryingFetch(
  input: string,
  init: (RequestInit & { method?: "GET" }) | undefined,
  fetchApi: typeof fetch = fetch,
  wait: Wait = defaultWait,
): Promise<Response> {
  let lastError: unknown = null;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    try {
      const response = await dedupedFetch(input, init, fetchApi);
      if (
        !RETRYABLE_STATUSES.has(response.status) ||
        attempt === MAX_ATTEMPTS - 1
      ) {
        return response;
      }
      // The body is never read on a retryable status, so release it rather
      // than leave it holding a connection. Deliberately not awaited: this is
      // one branch of a tee'd stream, and awaiting its cancellation blocks
      // until the other branch is drained, which nothing is going to do.
      void response.body?.cancel().catch(() => undefined);
      lastError = null;
    } catch (error) {
      if (isAbort(error)) throw error;
      if (attempt === MAX_ATTEMPTS - 1) throw error;
      lastError = error;
    }

    if (init?.signal?.aborted) {
      throw lastError ?? new DOMException("aborted", "AbortError");
    }
    await wait(RETRY_BASE_MS * 2 ** attempt);
  }

  // Unreachable: the loop either returns or throws on its final attempt. Kept
  // so the function has one type rather than one type and an implicit
  // undefined.
  throw lastError ?? new Error("retrying fetch exhausted its attempts");
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
