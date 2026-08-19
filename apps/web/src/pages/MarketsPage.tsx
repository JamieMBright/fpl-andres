import { AlertTriangle, CheckCircle2, CircleHelp } from "lucide-react";

import { dateTimeShort, percent, twoDecimal } from "../format";
import { RouteHeading } from "../components/RouteHeading";
import { TEAM_KITS } from "../kit/team-kits";
import {
  marketHealth,
  type MarketHealth,
  type TeamMarketHealth,
} from "../state/market-health";
import { useDocumentTitle } from "../state/use-document-title";
const clubNames = new Map(TEAM_KITS.map((team) => [team.shortName, team.name]));

function statusCopy(health: MarketHealth) {
  const hours =
    health.hoursUntilDeadline === null
      ? "an unreadable deadline"
      : `${Math.max(0, Math.round(health.hoursUntilDeadline))} hours to deadline`;
  if (health.verdict === "deadline-anomaly") {
    return {
      className: "error",
      icon: <AlertTriangle aria-hidden="true" size={20} />,
      title: "Player markets are late",
      detail: `${health.playerFixturesCovered}/${health.fixturesExpected} fixtures have usable player prices with ${hours}. I expected the round by now.`,
    };
  }
  if (health.verdict === "ready") {
    return {
      className: "ready",
      icon: <CheckCircle2 aria-hidden="true" size={20} />,
      title: "The round is covered",
      detail: `All ${health.fixturesExpected} fixtures carry the team and player markets I use.`,
    };
  }
  if (health.verdict === "unavailable") {
    return {
      className: "unavailable",
      icon: <CircleHelp aria-hidden="true" size={20} />,
      title: "No round to audit",
      detail:
        "The deadline or fixture list is unavailable, so I cannot grade market coverage.",
    };
  }
  return {
    className: "stale",
    icon: <CircleHelp aria-hidden="true" size={20} />,
    title: "Player markets are still opening",
    detail: `${health.playerFixturesCovered}/${health.fixturesExpected} fixtures have usable player prices with ${hours}.`,
  };
}

function providerLabel(status: string): string {
  const labels: Record<string, string> = {
    returned: "Returned",
    unvisited: "Not visited",
    "no-bookmaker": "No bookmaker",
    "no-markets": "No markets",
    "requested-markets-absent": "Player markets absent",
    "requested-markets-empty": "Player markets empty",
    "parse-error": "Response error",
  };
  return labels[status] ?? status;
}

function TeamRow({ team }: { team: TeamMarketHealth }) {
  const complete =
    team.teamMarketsCovered === team.teamMarketsExpected &&
    team.playerMarketsCovered === team.playerMarketsExpected &&
    team.playersQuoted >= team.quoteFloor;
  return (
    <tr className={complete ? "is-complete" : "is-gap"}>
      <th scope="row" translate="no">
        <strong>{team.club}</strong>
        <span>{clubNames.get(team.club) ?? team.club}</span>
      </th>
      <td className="mono" translate="no">
        {team.opponent} ({team.venue})
      </td>
      <td className="mono">{twoDecimal.format(team.expectedGoals)}</td>
      <td className="mono">{percent.format(team.cleanSheetProbability)}</td>
      <td className="mono">
        {team.teamMarketsCovered}/{team.teamMarketsExpected}
      </td>
      <td className="mono">
        {team.playerMarketsCovered}/{team.playerMarketsExpected}
      </td>
      <td className="mono">
        {team.playersQuoted}/{team.quoteFloor}
      </td>
      <td>
        <span
          className={`market-provider market-provider-${team.providerStatus}`}
        >
          {providerLabel(team.providerStatus)}
        </span>
        {team.unmatchedNames.length > 0 ? (
          <small>{team.unmatchedNames.join(", ")} did not match FPL</small>
        ) : null}
      </td>
      <td className="mono">
        {team.visitedAt
          ? dateTimeShort.format(new Date(team.visitedAt))
          : "Not checked"}
      </td>
    </tr>
  );
}

export default function MarketsPage() {
  const health = marketHealth();
  const status = statusCopy(health);

  useDocumentTitle(
    "Market coverage",
    "Bookmaker evidence by market, fixture and Premier League club.",
    { canonicalPath: null, robots: "noindex, nofollow" },
  );

  return (
    <section className="text-page markets-page" aria-label="Market coverage">
      <p className="eyebrow">Source health</p>
      <RouteHeading>Markets</RouteHeading>
      <p className="lede">
        What the next-gameweek projection can see from bookmakers, and where it
        is still leaning on the football record alone.
      </p>

      <div
        aria-label="Player market status"
        className={`evidence-banner evidence-banner-${status.className} market-verdict`}
        role="status"
      >
        {status.icon}
        <div>
          <strong>{status.title}</strong>
          <span>{status.detail}</span>
        </div>
      </div>

      <dl className="market-scoreboard">
        <div>
          <dt>Team-priced fixtures</dt>
          <dd className="mono">
            {health.teamFixturesCovered}/{health.fixturesExpected}
          </dd>
        </div>
        <div>
          <dt>Player-priced fixtures</dt>
          <dd className="mono">
            {health.playerFixturesCovered}/{health.fixturesExpected}
          </dd>
        </div>
        <div>
          <dt>Player check</dt>
          <dd className="mono">
            {dateTimeShort.format(new Date(health.playerMarketsAsOf))}
          </dd>
        </div>
        <div>
          <dt>Next deadline</dt>
          <dd className="mono">
            {health.deadline
              ? dateTimeShort.format(new Date(health.deadline))
              : "Unavailable"}
          </dd>
        </div>
      </dl>

      <section className="market-section" aria-labelledby="market-classes">
        <h2 id="market-classes">Markets used</h2>
        <div
          aria-label="Scrollable market coverage"
          className="squad-table-wrap market-table-wrap"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll wide evidence tables.
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Market</th>
                <th scope="col">Level</th>
                <th scope="col">Fixtures</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {health.markets.map((market) => (
                <tr key={market.key}>
                  <th scope="row">{market.label}</th>
                  <td>{market.kind === "team" ? "Fixture" : "Player"}</td>
                  <td className="mono">
                    {market.fixturesCovered}/{market.fixturesExpected}
                  </td>
                  <td>
                    <span
                      className={`market-state market-state-${market.status}`}
                    >
                      {market.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="market-section" aria-labelledby="team-coverage">
        <h2 id="team-coverage">Next gameweek by team</h2>
        <div
          aria-label="Scrollable team market coverage"
          className="squad-table-wrap market-table-wrap market-team-table"
          role="region"
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll wide evidence tables.
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Team</th>
                <th scope="col">Fixture</th>
                <th scope="col">xG</th>
                <th scope="col">CS</th>
                <th scope="col">Team</th>
                <th scope="col">Player</th>
                <th scope="col">Names</th>
                <th scope="col">Provider</th>
                <th scope="col">Checked</th>
              </tr>
            </thead>
            <tbody>
              {health.teams.map((team) => (
                <TeamRow key={`${team.kickoff}-${team.club}`} team={team} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="market-source-note">
        Team prices observed{" "}
        {dateTimeShort.format(new Date(health.fixtureMarketsAsOf))}. Player
        prices observed{" "}
        {dateTimeShort.format(new Date(health.playerMarketsAsOf))}. A
        named-player set needs 18 matched names before silence can count as
        evidence that somebody is absent.
      </p>
    </section>
  );
}
