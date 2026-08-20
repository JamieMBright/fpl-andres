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
          <h2 id="api-endpoints">Endpoints</h2>
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
        <h2 id="api-example">Python example</h2>
        <pre aria-label="API response example">
          {`import requests

BASE = "https://fpl-andres.vercel.app"

response = requests.get(
    f"{BASE}/api/recommendations/xstart",
    timeout=10,
)
response.raise_for_status()

payload = response.json()
for team in payload["teams"]:
    if team["club"] == "LEE":
        for player in team["players"][:5]:
            print(
                player["name"],
                player["startProbability"],
                player["evidence"],
            )`}
        </pre>
        <p>
          The endpoints are public, read-only and rate-limited. Check
          <code>RateLimit-Remaining</code> before polling again; a limit
          response is HTTP <code>429</code> and includes
          <code>Retry-After</code>.
        </p>
      </section>
    </section>
  );
}
