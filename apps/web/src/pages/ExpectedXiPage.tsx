import { Activity, CircleHelp, LineChart } from "lucide-react";
import { useState } from "react";

import { CeefaxShirt } from "../components/CeefaxShirt";
import { InfoMarker } from "../components/InfoMarker";
import { RouteHeading } from "../components/RouteHeading";
import { XStartCalibration } from "../components/XStartCalibration";
import { dateTimeShort, percent } from "../format";
import { TEAM_KITS } from "../kit/team-kits";
import {
  expectedXi,
  type ExpectedXiPlayer,
  type ExpectedXiTeam,
} from "../state/expected-xi";
import { useDocumentTitle } from "../state/use-document-title";
import { PLAYERS_BY_ELEMENT_ID } from "../state/season-solver";

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

function availabilityLabel(player: ExpectedXiPlayer): string {
  const labels: Record<string, string> = {
    d: "Doubtful",
    i: "Injured",
    s: "Suspended",
    u: "Unavailable",
    n: "Not in squad",
  };
  const status = labels[player.availabilityStatus ?? ""] ?? "Flagged";
  return player.chanceOfPlaying === null
    ? status
    : `${status} · ${player.chanceOfPlaying}% play`;
}

function PlayerRow({ player }: { player: ExpectedXiPlayer }) {
  return (
    <li>
      <span className="expected-xi-position mono">{player.position}</span>
      <span className="expected-xi-name">
        {player.name}
        {player.availabilityStatus && player.availabilityStatus !== "a" ? (
          <small className="expected-xi-availability mono">
            {availabilityLabel(player)}
          </small>
        ) : null}
      </span>
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
          {team.validation ? (
            <p className="expected-xi-validation mono">
              GW1 check · {team.validation.topElevenHits}/
              {team.validation.actualStarters} starters
              <InfoMarker label={`${team.club} GW1 xStart check`}>
                Frozen XI misses:{" "}
                {team.validation.selected
                  .filter((row) => !row.started)
                  .map(
                    (row) =>
                      `${PLAYERS_BY_ELEMENT_ID.get(row.elementId)?.name ?? row.elementId} (${percent.format(row.probability)})`,
                  )
                  .join(", ") || "none"}
                . Actual starters left out:{" "}
                {team.validation.missedStarters
                  .map(
                    (row) =>
                      `${PLAYERS_BY_ELEMENT_ID.get(row.elementId)?.name ?? row.elementId} (${percent.format(row.probability)})`,
                  )
                  .join(", ") || "none"}
                . Brier {team.validation.brier.toFixed(3)} is the mean squared
                probability error across all {team.validation.count} club
                candidates. Lower is better.
              </InfoMarker>
            </p>
          ) : null}
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
      {team.availabilityFlags.length > 0 ? (
        <div className="expected-xi-flags">
          <strong>FPL flags</strong>
          <ul>
            {team.availabilityFlags.map((player) => (
              <li key={player.id}>
                <span>{player.name}</span>
                <span className="expected-xi-availability mono">
                  {availabilityLabel(player)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="expected-xi-source mono">
        {team.updatedAt
          ? dateTimeShort.format(new Date(team.updatedAt))
          : "Not checked"}
        {team.unmatchedNames.length > 0
          ? ` · ${team.unmatchedNames.length} unmatched`
          : " · matched"}
      </p>
      {team.teamSheetEvidence === "unavailable" ? (
        <p className="expected-xi-source expected-xi-source-warning">
          No dated team-sheet source is attached. Bookmaker coverage is market
          evidence, not confirmation that this XI starts.
        </p>
      ) : null}
    </section>
  );
}

export default function ExpectedXiPage() {
  const xi = expectedXi();
  const [view, setView] = useState<"current" | "history">("current");

  useDocumentTitle(
    "Expected XI",
    "Team-by-team starting probability with market, model and prior evidence separated.",
    { canonicalPath: null, robots: "noindex, nofollow" },
  );

  return (
    <section className="text-page expected-xi-page" aria-label="Expected XI">
      <p className="eyebrow">Team sheets</p>
      <RouteHeading>xStart GW{xi.event}</RouteHeading>
      <p className="lede">
        My current xStart read, split by market signal, model record, manual
        team news and role prior.
      </p>

      <fieldset className="xstart-event-choice">
        <legend>Gameweek view</legend>
        <label>
          <input
            checked={view === "current"}
            name="xstart-event"
            onChange={() => setView("current")}
            type="radio"
          />
          <span>GW{xi.event} forecast</span>
        </label>
        <label>
          <input
            checked={view === "history"}
            name="xstart-event"
            onChange={() => setView("history")}
            type="radio"
          />
          <span>GW1 score</span>
        </label>
      </fieldset>

      {view === "history" ? (
        <XStartCalibration />
      ) : (
        <>
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
                {xi.teams.reduce(
                  (total, team) => total + team.starters.length,
                  0,
                )}
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
        </>
      )}
    </section>
  );
}
