import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

const ENDPOINTS = [
  [
    "GET /api/recommendations/latest",
    "Captain, transfers, bench order and evidence state.",
  ],
  [
    "GET /api/recommendations/xstart",
    "Team-by-team xStart and player evidence.",
  ],
  [
    "GET /api/recommendations/markets",
    "Fixture and player market coverage diagnostics.",
  ],
  [
    "GET /api/recommendations/meta",
    "Model version, artifact versions and source freshness.",
  ],
] as const;

export default function ApiPage() {
  useDocumentTitle(
    "API",
    "Read-only FPL Andres recommendation and evidence API documentation.",
    { canonicalPath: "/api-docs" },
  );

  return (
    <section className="text-page api-page" aria-label="API documentation">
      <p className="eyebrow">Integration</p>
      <RouteHeading>API</RouteHeading>
      <p className="lede">
        Read the current recommendations and their evidence. No endpoint makes a
        transfer, changes a squad or writes private team state.
      </p>

      <div className="api-grid">
        <section aria-labelledby="api-read-only">
          <h2 id="api-read-only">Read-only contract</h2>
          <p>
            Responses are artifact-backed. Each suggestion carries model
            version, source timestamps and an evidence state. Missing evidence
            returns partial or unavailable, not a guess.
          </p>
        </section>
        <section aria-labelledby="api-endpoints">
          <h2 id="api-endpoints">Endpoints planned</h2>
          <dl className="api-endpoints">
            {ENDPOINTS.map(([path, description]) => (
              <div key={path}>
                <dt className="mono">{path}</dt>
                <dd>{description}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>

      <section className="api-example" aria-labelledby="api-example">
        <h2 id="api-example">Response shape</h2>
        <pre aria-label="API response example">
          {`{
  "schemaVersion": 1,
  "generatedAt": "2026-08-19T21:00:00Z",
  "modelVersion": "8.3",
  "deadline": "2026-08-21T17:30:00Z",
  "recommendations": {
    "captain": {
      "name": "Player",
      "expectedPoints": 6.4,
      "evidence": "inferred",
      "sources": ["season-inputs", "fixture-odds", "player-odds"]
    }
  }
}`}
        </pre>
      </section>
    </section>
  );
}
