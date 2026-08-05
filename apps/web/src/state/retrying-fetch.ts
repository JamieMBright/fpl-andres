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

/**
 * 250ms then 500ms was too short to outlive anything that actually happens.
 * A cold serverless instance takes seconds to come up and FPL sheds load for
 * longer than that, so the old schedule reliably spent all three attempts
 * inside the same bad second and reported the outage anyway.
 *
 * The jitter is not decoration. Every reader whose page failed at the same
 * moment retried on the same fixed schedule, so the retries arrived together
 * and the recovering upstream met a second synchronised wave.
 */
const RETRY_BASE_MS = 1_000;
const JITTER_RATIO = 0.4;

/** Statuses the proxy itself emits when the failure is worth asking again. */
const RETRYABLE_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);

/**
 * A 502 whose body names `unreachable` is the proxy reporting that it already
 * made three upstream attempts with backoff and had none of them answer. An
 * immediate retry here does not add a chance of success; it adds three more
 * upstream fetches of a multi-megabyte document to an upstream that is already
 * failing. The client's job at that point is to stop and say so.
 */
async function isExhaustedProxyFailure(response: Response): Promise<boolean> {
  if (response.status !== 502) return false;
  try {
    const payload = (await response.clone().json()) as { reason?: unknown };
    return payload.reason === "unreachable";
  } catch {
    return false;
  }
}

export interface RetryingFetchOptions {
  fetchApi?: typeof fetch;
  wait?: (milliseconds: number) => Promise<void>;
  attempts?: number;
  /** Seam for the jitter, so a test can pin the schedule. */
  random?: () => number;
}

export function retryingFetch(
  options: RetryingFetchOptions = {},
): typeof fetch {
  const fetchApi = options.fetchApi ?? fetch;
  const wait = options.wait;
  const attempts = options.attempts ?? MAX_ATTEMPTS;
  const random = options.random ?? Math.random;
  if (!Number.isInteger(attempts) || attempts < 1) {
    throw new RangeError(
      `attempts must be a positive integer (got ${attempts})`,
    );
  }

  return async function fetchWithRetries(input, init) {
    const method = (init?.method ?? "GET").toUpperCase();
    if (method !== "GET") {
      throw new TypeError(
        `retryingFetch only wraps idempotent GET requests (got ${method})`,
      );
    }

    const signal = init?.signal instanceof AbortSignal ? init.signal : null;

    let lastError: unknown = null;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const response = await fetchApi(input, init);
        if (
          !RETRYABLE_STATUSES.has(response.status) ||
          attempt === attempts - 1 ||
          (await isExhaustedProxyFailure(response))
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
      // Make the backoff delay abortable so navigation/unmount fails fast.
      const delayMs = Math.round(
        RETRY_BASE_MS *
          2 ** attempt *
          (1 - JITTER_RATIO / 2 + random() * JITTER_RATIO),
      );
      if (wait) {
        await wait(delayMs);
      } else {
        await new Promise<void>((resolve, reject) => {
          const id = setTimeout(resolve, delayMs);
          if (signal) {
            signal.addEventListener(
              "abort",
              () => {
                clearTimeout(id);
                reject(
                  new DOMException("The operation was aborted.", "AbortError"),
                );
              },
              { once: true },
            );
          }
        });
      }
    }
    // Unreachable: the final attempt either returns or throws above. Kept
    // honest rather than asserted away.
    throw lastError instanceof Error
      ? lastError
      : new TypeError("Failed to fetch");
  };
}
