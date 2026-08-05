/**
 * The last copy of a public FPL document that was known to be good.
 *
 * The proxy in `fpl-proxy.ts` used to have exactly two answers for a public
 * document: the bytes FPL just sent, or a 502. FPL sheds load around deadlines
 * and price changes, and a cold serverless instance can spend its whole budget
 * on one slow read of a multi-megabyte bootstrap. Either produced a dead page
 * for a document that is identical for every caller and changes a handful of
 * times an hour -- so the outage was being served in full, when a copy from
 * four minutes ago would have answered the question.
 *
 * This is that copy. It is deliberately separate from the fresh TTL in
 * `SourceCache`: the TTL answers "may I reuse this instead of asking?", which
 * has to be short, and this answers "FPL is not answering, do I have anything
 * at all?", which should be measured in hours.
 *
 * Two rules keep it honest.
 *
 * Only a 200 is retained. A 404 or a 503 is not a document, and holding one
 * would mean serving an error for hours after the real one cleared.
 *
 * A served copy is never allowed to look fresh. `X-FPL-Stale-Age` and
 * `X-FPL-Captured-At` go out with it and the body is not touched, so a reader
 * -- and the UI -- can tell the difference between what FPL says now and what
 * it said before it stopped answering. Presenting a stale body as current is
 * the one failure mode worse than the 502 this replaces.
 *
 * Module scope, so it lives as long as the warm instance that holds it. That
 * is enough for the common incident and nothing more: a cold start begins with
 * an empty store and falls back to the same error as before.
 */

const MAX_ENTRIES = 8;
const DEFAULT_RETENTION_MS = 6 * 60 * 60 * 1_000;

export interface StoredDocument {
  body: ArrayBuffer;
  capturedAt: number;
}

export class FplDocumentStore {
  readonly #documents = new Map<string, StoredDocument>();

  constructor(
    private readonly now: () => number = Date.now,
    private readonly retentionMs: number = DEFAULT_RETENTION_MS,
  ) {}

  put(key: string, body: ArrayBuffer): void {
    // Re-insert rather than mutate, so the Map's insertion order stays a
    // usable approximation of least-recently-written for the eviction below.
    this.#documents.delete(key);
    this.#documents.set(key, { body, capturedAt: this.now() });
    if (this.#documents.size > MAX_ENTRIES) {
      const oldest = this.#documents.keys().next();
      if (!oldest.done) this.#documents.delete(oldest.value);
    }
  }

  /** The retained copy, or null when there is none or it is past retention. */
  get(key: string): StoredDocument | null {
    const stored = this.#documents.get(key);
    if (stored === undefined) return null;
    if (this.now() - stored.capturedAt > this.retentionMs) {
      this.#documents.delete(key);
      return null;
    }
    return stored;
  }

  clear(): void {
    this.#documents.clear();
  }

  get size(): number {
    return this.#documents.size;
  }
}
