import { AlertTriangle, CheckCircle2, CircleHelp } from "lucide-react";

import { dateTimeShort, percent, twoDecimal } from "../format";
import { RouteHeading } from "../components/RouteHeading";
import { TEAM_KITS } from "../kit/team-kits";
import {
  marketHealth,
  type MarketHealth,
  type PlayerMarketHealth,
  type TeamMarketHealth,
} from "../state/market-health";
import { useDocumentTitle } from "../state/use-document-title";
const clubNames = new Map(TEAM_KITS.map((team) => [team.shortName, team.name]));

function playerMarketCoverage(health: MarketHealth) {
  const playerMarkets = health.markets.filter(
    (market) => market.kind === "player",
  );
  const complete = playerMarkets.filter(
    (market) => market.status === "complete",
  );
  const incomplete = playerMarkets.filter(
    (market) => market.status !== "complete",
  );
  return { playerMarkets, complete, incomplete };
}

export function statusCopy(health: MarketHealth) {
  const hours =
    health.hoursUntilDeadline === null
      ? "an unreadable deadline"
      : `${Math.max(0, Math.round(health.hoursUntilDeadline))} hours to deadline`;
  const playerCoverage = playerMarketCoverage(health);
  const incompleteMarkets = playerCoverage.incomplete
    .map((market) => market.label)
    .join(", ");
  const playerClassCoverage = `${playerCoverage.complete.length}/${playerCoverage.playerMarkets.length}`;
  if (health.verdict === "deadline-anomaly") {
    const detail =
      health.playerFixturesCovered < health.fixturesExpected
        ? `${health.playerFixturesCovered}/${health.fixturesExpected} fixtures have usable player prices with ${hours}. I expected the round by now.`
        : `${health.playerFixturesCovered}/${health.fixturesExpected} fixtures have player prices, but only ${playerClassCoverage} player markets are complete with ${hours}${incompleteMarkets ? `: ${incompleteMarkets}` : ""}.`;
    return {
      className: "error",
      icon: <AlertTriangle aria-hidden="true" size={20} />,
      title: "Player markets are late",
      detail,
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
      title:
        health.event === null
          ? "No round to audit"
          : `GW${health.event} prices unavailable`,
      detail:
        health.event === null
          ? "The deadline or fixture list is unavailable, so I cannot grade market coverage."
          : `The shipped fixture book belongs to an earlier round. I will not call settled prices GW${health.event} evidence.`,
    };
  }
  return {
    className: "stale",
    icon: <CircleHelp aria-hidden="true" size={20} />,
    title: "Player markets are still opening",
    detail:
      health.playerFixturesCovered === health.fixturesExpected &&
      playerCoverage.incomplete.length > 0
        ? `${health.playerFixturesCovered}/${health.fixturesExpected} fixtures have player prices; ${playerClassCoverage} player markets are complete.`
        : `${health.playerFixturesCovered}/${health.fixturesExpected} fixtures have usable player prices with ${hours}.`,
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

function marketNumber(value: number | null, kind: "count" | "probability") {
  if (value === null) return "—";
  return kind === "probability"
    ? percent.format(value)
    : twoDecimal.format(value);
}

function PlayerMarketRow({ player }: { player: PlayerMarketHealth }) {
  return (
    <tr>
      <th scope="row">
        <strong>{player.name}</strong>
        <span>{player.quotedName}</span>
      </th>
      <td className="mono">{player.position ?? "—"}</td>
      <td className="mono">
        {player.startRate === null ? "—" : percent.format(player.startRate)}
      </td>
      <td className="mono">{player.books ?? "—"}</td>
      <td className="mono">
        {marketNumber(player.markets["Anytime scorer"] ?? null, "probability")}
      </td>
      <td className="mono">
        {marketNumber(player.markets["Anytime assist"] ?? null, "probability")}
      </td>
      <td className="mono">
        {marketNumber(player.markets["Any card"] ?? null, "probability")}
      </td>
      <td className="mono">
        {marketNumber(player.markets["Total shots"] ?? null, "count")}
      </td>
      <td className="mono">
        {marketNumber(player.markets["Shots on target"] ?? null, "count")}
      </td>
    </tr>
  );
}

function TeamRow({ team }: { team: TeamMarketHealth }) {
  const complete =
    team.teamMarketsCovered === team.teamMarketsExpected &&
    team.playerMarketsCovered === team.playerMarketsExpected &&
    team.playersQuoted >= team.quoteFloor;
  return (
    <>
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
      <tr className="market-player-detail-row">
        <td colSpan={9}>
          <details>
            <summary>
              {team.players.length} matched player quote
              {team.players.length === 1 ? "" : "s"}
            </summary>
            <div
              aria-label="Scrollable player markets"
              className="squad-table-wrap market-player-table"
              role="region"
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll wide evidence tables.
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">Player</th>
                    <th scope="col">Pos</th>
                    <th scope="col">xStart</th>
                    <th scope="col">Books</th>
                    <th scope="col">Goal</th>
                    <th scope="col">Assist</th>
                    <th scope="col">Card</th>
                    <th scope="col">Shots</th>
                    <th scope="col">SoT</th>
                  </tr>
                </thead>
                <tbody>
                  {team.players.length > 0 ? (
                    team.players.map((player) => (
                      <PlayerMarketRow
                        key={`${team.kickoff}-${team.club}-${player.elementId ?? player.quotedName}`}
                        player={player}
                      />
                    ))
                  ) : (
                    <tr>
                      <td colSpan={9}>
                        No matched player prices for this team.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </details>
        </td>
      </tr>
    </>
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
        What the GW{health.event ?? "—"} projection can see from bookmakers, and
        where it is still leaning on the football record alone.
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
        <h2 id="team-coverage">GW{health.event ?? "—"} by team</h2>
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
