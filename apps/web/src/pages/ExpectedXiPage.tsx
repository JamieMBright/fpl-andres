import { Activity, CircleHelp, LineChart } from "lucide-react";

import { CeefaxShirt } from "../components/CeefaxShirt";
import { RouteHeading } from "../components/RouteHeading";
import { dateTimeShort, percent } from "../format";
import { TEAM_KITS } from "../kit/team-kits";
import {
  expectedXi,
  type ExpectedXiPlayer,
  type ExpectedXiTeam,
} from "../state/expected-xi";
import { useDocumentTitle } from "../state/use-document-title";

const kitsByShortName = new Map(
  TEAM_KITS.map((team) => [team.shortName, team]),
);

function anchorFor(club: string): string {
  return `expected-xi-${club.toLowerCase()}`;
}

function evidenceLabel(player: ExpectedXiPlayer): string {
  if (player.evidence === "manual") return "Manual";
  if (player.evidence === "market") return "Market";
  if (player.evidence === "prior") return "Prior";
  return "Model";
}

function evidenceIcon(player: ExpectedXiPlayer) {
  if (player.evidence === "manual")
    return <CircleHelp aria-hidden="true" size={14} />;
  if (player.evidence === "market")
    return <LineChart aria-hidden="true" size={14} />;
  if (player.evidence === "prior")
    return <CircleHelp aria-hidden="true" size={14} />;
  return <Activity aria-hidden="true" size={14} />;
}

function PlayerRow({ player }: { player: ExpectedXiPlayer }) {
  return (
    <li>
      <span className="expected-xi-position mono">{player.position}</span>
      <span className="expected-xi-name">{player.name}</span>
      <details className="expected-xi-probability">
        <summary className="mono">
          <span>xStart</span> {percent.format(player.startProbability)}
        </summary>
        <div className="expected-xi-explain">
          <strong>{player.explanation.title}</strong>
          <dl>
            {player.explanation.factors.map((factor) => (
              <div key={`${player.id}-${factor.label}-${factor.value}`}>
                <dt>{factor.label}</dt>
                <dd>
                  <span className="mono">{factor.value}</span>
                  {factor.detail}
                </dd>
              </div>
            ))}
          </dl>
          <small>
            {player.explanation.updatedAt
              ? `Updated ${dateTimeShort.format(new Date(player.explanation.updatedAt))}`
              : "No source timestamp"}
          </small>
        </div>
      </details>
      <span
        className={`expected-xi-evidence expected-xi-evidence-${player.evidence}`}
      >
        {evidenceIcon(player)}
        {evidenceLabel(player)}
      </span>
    </li>
  );
}

function TeamSection({ team }: { team: ExpectedXiTeam }) {
  const kit = kitsByShortName.get(team.club);
  return (
    <section
      aria-labelledby={`${anchorFor(team.club)}-heading`}
      className="expected-xi-team"
      id={anchorFor(team.club)}
    >
      <header>
        {kit ? (
          <CeefaxShirt className="expected-xi-shirt" kit={kit} label={null} />
        ) : null}
        <div>
          <h2 id={`${anchorFor(team.club)}-heading`}>
            <span translate="no">{team.club}</span> {team.name}
          </h2>
          <p>
            {percent.format(team.averageStartProbability)} average xStart.{" "}
            {team.playersQuoted}/{team.quoteFloor} player quotes.
          </p>
        </div>
        <span
          className={`market-provider market-provider-${team.marketStatus}`}
        >
          {team.marketStatus}
        </span>
      </header>
      <div className="expected-xi-columns">
        <div>
          <h3>Likely XI</h3>
          <ol className="expected-xi-list">
            {team.starters.map((player) => (
              <PlayerRow key={player.id} player={player} />
            ))}
          </ol>
        </div>
        <div>
          <h3>Next in</h3>
          <ol className="expected-xi-list expected-xi-reserves">
            {team.reserves.map((player) => (
              <PlayerRow key={player.id} player={player} />
            ))}
          </ol>
        </div>
      </div>
      <p className="expected-xi-source mono">
        {team.updatedAt
          ? dateTimeShort.format(new Date(team.updatedAt))
          : "Not checked"}
        {team.unmatchedNames.length > 0
          ? ` · ${team.unmatchedNames.length} unmatched`
          : " · matched"}
      </p>
    </section>
  );
}

export default function ExpectedXiPage() {
  const xi = expectedXi();

  useDocumentTitle(
    "Expected XI",
    "Team-by-team starting probability with market, model and prior evidence separated.",
    { canonicalPath: null, robots: "noindex, nofollow" },
  );

  return (
    <section className="text-page expected-xi-page" aria-label="Expected XI">
      <p className="eyebrow">Team sheets</p>
      <RouteHeading>Expected XI</RouteHeading>
      <p className="lede">
        My current xStart read, split by market signal, model record, manual
        team news and role prior.
      </p>

      <nav aria-label="Expected XI clubs" className="expected-xi-clubs">
        {xi.teams.map((team) => {
          const kit = kitsByShortName.get(team.club);
          return (
            <a
              key={team.club}
              href={`#${anchorFor(team.club)}`}
              title={team.name}
            >
              {kit ? (
                <CeefaxShirt
                  className="expected-xi-club-shirt"
                  kit={kit}
                  label={team.name}
                />
              ) : null}
              <span translate="no">{team.club}</span>
            </a>
          );
        })}
      </nav>

      <dl className="market-scoreboard expected-xi-scoreboard">
        <div>
          <dt>Teams</dt>
          <dd className="mono">{xi.teams.length}</dd>
        </div>
        <div>
          <dt>Starters</dt>
          <dd className="mono">
            {xi.teams.reduce((total, team) => total + team.starters.length, 0)}
          </dd>
        </div>
        <div>
          <dt>Market check</dt>
          <dd className="mono">
            {xi.marketUpdatedAt
              ? dateTimeShort.format(new Date(xi.marketUpdatedAt))
              : "Unavailable"}
          </dd>
        </div>
        <div>
          <dt>Model build</dt>
          <dd className="mono">
            {dateTimeShort.format(new Date(xi.generatedAt))}
          </dd>
        </div>
      </dl>

      <div className="expected-xi-teams">
        {xi.teams.map((team) => (
          <TeamSection key={team.club} team={team} />
        ))}
      </div>
    </section>
  );
}
