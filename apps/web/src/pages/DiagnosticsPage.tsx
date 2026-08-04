import { useCallback, useEffect, useRef, useState } from "react";

import { RouteHeading } from "../components/RouteHeading";
import {
  overallVerdict,
  PROBE_TARGETS,
  probe,
  type ProbeResult,
} from "../state/diagnostics";
import { useDocumentTitle } from "../state/use-document-title";

/**
 * What is actually wrong with the deployed API, readable on a phone.
 *
 * The dev server serves `/api/*` from a Vite plugin, so a route can be healthy
 * locally and broken in production. Diagnosing that has needed a terminal, and
 * whoever notices the failure is usually not sitting at one. This runs the same
 * probes the deployed smoke suite runs, from the browser that is already open,
 * and names the cause rather than reporting that something failed.
 *
 * Deliberately unlinked from the navigation: it is an operator tool, not a
 * feature, and it is reached by typing `/diagnostics`.
 */
export default function DiagnosticsPage() {
  useDocumentTitle(
    "Diagnostics",
    "Probe the deployed API and name what is wrong.",
  );

  const [results, setResults] = useState<ProbeResult[]>([]);
  const [running, setRunning] = useState(false);
  const [ranAt, setRanAt] = useState<string | null>(null);
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  const run = useCallback(async () => {
    setRunning(true);
    setResults([]);
    // Appended one at a time rather than awaited as a batch: on a slow mobile
    // connection a page that shows nothing for fifteen seconds looks broken
    // itself, which is the opposite of what a diagnostic should do.
    for (const target of PROBE_TARGETS) {
      const result = await probe(target);
      if (!live.current) return;
      setResults((current) => [...current, result]);
    }
    if (!live.current) return;
    setRanAt(new Date().toISOString());
    setRunning(false);
  }, []);

  const complete = !running && results.length > 0;

  return (
    <section className="text-page diagnostics-page">
      <p className="eyebrow">Diagnostics</p>
      <RouteHeading>What is wrong with the API?</RouteHeading>
      <p>
        These are the exact calls the analysis tab makes on first paint, run
        from this browser against this deployment. A route that works on a
        developer machine and fails here is the difference between the dev
        server and Vercel&rsquo;s router.
      </p>

      <p>
        <button type="button" onClick={() => void run()} disabled={running}>
          {running
            ? "Probing\u2026"
            : results.length > 0
              ? "Probe again"
              : "Run the probes"}
        </button>
      </p>

      <div aria-live="polite">
        {complete && (
          <p className="diagnostics-verdict">
            <strong>{overallVerdict(results)}</strong>
          </p>
        )}

        <ul className="diagnostics-list">
          {results.map((result) => (
            <li
              key={result.id}
              className={`diagnostics-item diagnostics-item--${result.verdict}`}
            >
              <h2>
                {result.verdict === "ok" ? "\u2713" : "\u2717"} {result.label}
              </h2>
              <p className="diagnostics-meta">
                <code>{result.path}</code> &middot;{" "}
                {result.status === null
                  ? "no response"
                  : `HTTP ${String(result.status)}`}{" "}
                &middot; {String(result.durationMs)} ms
              </p>
              <p>{result.summary}</p>
              <dl className="diagnostics-detail">
                {result.contentType !== null && (
                  <>
                    <dt>Content type</dt>
                    <dd>{result.contentType}</dd>
                  </>
                )}
                {result.vercelError !== null && (
                  <>
                    <dt>Vercel error</dt>
                    <dd>{result.vercelError}</dd>
                  </>
                )}
                {result.reason !== null && (
                  <>
                    <dt>Reason</dt>
                    <dd>{result.reason}</dd>
                  </>
                )}
                {result.requestId !== null && (
                  <>
                    <dt>Request id</dt>
                    <dd>
                      <code>{result.requestId}</code>
                    </dd>
                  </>
                )}
              </dl>
            </li>
          ))}
        </ul>

        {running && (
          <p>Probing {String(PROBE_TARGETS.length)} routes&hellip;</p>
        )}
      </div>

      {complete && ranAt !== null && (
        <p className="diagnostics-meta">
          Run at {ranAt}. Quote a request id when reading the Vercel logs; every
          failure line is JSON carrying the same field.
        </p>
      )}
    </section>
  );
}
