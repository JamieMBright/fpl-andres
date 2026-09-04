import { ArrowRight } from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { CeefaxShirt } from "../components/CeefaxShirt";
import { InfoMarker } from "../components/InfoMarker";
import { PlanStep } from "../components/PlanStep";
import { DeclaredSquadNote } from "../components/DeclaredSquadNote";
import { AnalysisResult } from "../components/AnalysisResult";
import { analysisAnnouncement } from "../state/team-analysis-messages";
import {
  readDeclaredSquad,
  readLastTeam,
  readTeamIdHistory,
  rememberTeam,
  saveDeclaredSquad,
  type OpeningDecision,
} from "../state/declared-squad";
import { DeclaredTransferForm } from "../components/DeclaredTransferForm";
import { DeclaredChipsForm } from "../components/DeclaredChipsForm";
import { LiveSquad } from "../components/LiveSquad";
import { MiniLeagueThreats } from "../components/MiniLeagueThreats";
import { RankObjectiveForm } from "../components/RankObjectiveForm";
import { PlayerDetail } from "../components/PlayerDetail";
import { RouteHeading } from "../components/RouteHeading";
import { Scorecard } from "../components/Scorecard";
import { deadlineDay, money, timestamp } from "../format";
import { kitForShortName } from "../kit/team-kits";
import type { SolvedGameweek } from "../state/season-solver";
import { PLAYERS_BY_ELEMENT_ID, startFromCodes } from "../state/season-solver";
import { encodeSquad } from "../state/squad-code";
import { readScorecard, recordCall, settleCall } from "../state/scorecard";
import { useSeasonSolve } from "../state/use-season-solve";
import type {
  TeamStartFailure,
  TeamStartStatus,
} from "../state/use-team-start";
import {
  currentPlanningEvent,
  PRE_SEASON_EVENT,
  useTeamPlan,
} from "../state/use-team-start";
import type {
  ChipCall,
  Confidence,
  PlanGameweek,
  PlanPlayer,
} from "../state/season-plan";
import { pairTransfers, readSeasonPlan } from "../state/season-plan";
import {
  chipCallsByEvent,
  chipCallsFor,
  plannedRebuilds,
  resolveChipClashes,
} from "../state/season-chips";
import {
  CHIP_NAMES,
  NO_CHIPS,
  readDeclaredChips,
  type DeclaredChips,
} from "../state/declared-chips";
import {
  chasesLeague,
  readRankObjective,
  type RankObjective,
} from "../state/rank-objective";
import {
  CAPTAINCY_VERDICT,
  captainLine,
  chipReason,
  confidenceReason,
  deadlineAdvice,
  fixtureReason,
  moneyLines,
  moveLines,
} from "../state/plan-reasons";

const Gw1ReviewPitch = lazy(() =>
  import("../components/Gw1ReviewPitch").then((module) => ({
    default: module.Gw1ReviewPitch,
  })),
);
const GW1_REVIEW_EVENT = 1;
const GW1_REVIEW_ENTRY_ID = 2_822_737;
import { useDocumentTitle } from "../state/use-document-title";
import {
  fixtureEvidenceForClubs,
  type FixtureEvidence,
} from "../state/fixture-evidence";

/** What a chip should return before it is worth planning a season around. */
const CHIP_TARGET = 20;

/** Kept beside the list below; `plan-caveats.test.tsx` fails if they disagree. */
const CAVEAT_COUNT = "Six";

/**
 * The plan's own rating for a player's tie that week.
 *
 * The page had this all along in `week.difficulty` and never handed it over, so
 * every player opened from a card claimed there was no rating for his fixtures
 * while the card beside him was rating them.
 */
function planDifficulty(
  week: PlanGameweek,
  player: PlanPlayer,
): { rating: number; opponents: readonly string[] } | null {
  const rating = week.difficulty[player.club];
  return rating === undefined || rating === null
    ? null
    : { rating, opponents: week.opponents[player.club] ?? [] };
}

/** Roughly the horizon the model has calibrated. The rest is drawn on ask. */
const INITIAL_WEEKS = 8;

const TEAM_FAILURE: Record<TeamStartFailure, string> = {
  not_a_team_id: "That is not a Team ID. It is the number in your FPL URL.",
  unreachable: "I could not reach FPL for that squad, so I am not guessing it.",
  no_processed_event:
    "FPL has not processed a gameweek for that squad yet, so there are no picks to read. Build your fifteen on your team page and I will plan from it.",
  squad_not_recognised:
    "That squad has a player I do not carry, so I will not solve fourteen fifteenths of it.",
  squad_not_projectable:
    "Your locked-in fifteen has a player I hold no Premier League record for — a promoted-club debutant or an arrival from abroad. I can hold him in a squad but I cannot project him, so rather than plan a season around a blank I am showing you nothing. Swap him on your team page and the plan becomes yours.",
};

/**
 * Your season, not the opening squad's.
 *
 * The plan below is what the optimal opening squad does with the year, which is
 * nobody's season after the first deadline. A Team ID replaces it with the same
 * solve run on your own fifteen.
 */
/** Exported for test: rendering the whole rail to exercise a form is too slow. */
export function TeamEntry({
  team,
  params,
  onChange,
}: {
  team: TeamStartStatus;
  params: URLSearchParams;
  onChange: (next: URLSearchParams, options?: { replace: boolean }) => void;
}) {
  const [entered, setEntered] = useState(params.get("team") ?? "");
  const teamIdHistory = useMemo(
    () => readTeamIdHistory(window.localStorage),
    [],
  );

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams(params);
    const trimmed = entered.trim();
    if (trimmed) next.set("team", trimmed);
    else next.delete("team");
    onChange(next, { replace: true });
  };

  return (
    <form className="plan-team" onSubmit={submit}>
      <label htmlFor="plan-team-id">Your Team ID</label>
      <input
        id="plan-team-id"
        name="team"
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        autoComplete="off"
        list="plan-team-id-history"
        placeholder="1234567"
        value={entered}
        onChange={(event) => setEntered(event.target.value)}
      />
      <datalist id="plan-team-id-history">
        {teamIdHistory.map((entryId) => (
          <option key={entryId} value={entryId} />
        ))}
      </datalist>
      <button type="submit">Plan my season</button>
      <p className="plan-team-note" role="status">
        {team.status === "loading"
          ? "Reading your squad."
          : team.status === "ready"
            ? (team.source === "declared"
                ? `Your declared fifteen, solved from gameweek ${String(team.event)}.`
                : `Your fifteen, solved from gameweek ${String(team.event)}.`) +
              (team.declared.length > 0
                ? ` Plus ${String(team.declared.length)} transfer${team.declared.length === 1 ? "" : "s"} you told me about.`
                : "")
            : team.status === "failed"
              ? TEAM_FAILURE[team.reason]
              : "Leave it blank for the optimal opening squad's season."}
      </p>
      {team.status === "failed" && team.reason === "no_processed_event" ? (
        // The message named a page and gave no way to reach it, which is a dead
        // end in the one state every manager hits before the season starts.
        <p className="plan-team-note">
          <Link to={`/team/${entered.trim()}`}>
            Build your fifteen for team {entered.trim()}
          </Link>
        </p>
      ) : null}
    </form>
  );
}

/**
 * The club shirt. Silent to assistive technology because the short name is
 * printed beside it, and three pairs of clubs render identically anyway.
 */
function Shirt({ club }: { club: string }) {
  const kit = kitForShortName(club);
  return kit ? (
    <CeefaxShirt className="plan-shirt" kit={kit} label={null} />
  ) : (
    <span className="plan-shirt" aria-hidden="true" />
  );
}

/**
 * Home in capitals, away in lower case. A column of "(H)" and "(A)" is four
 * more characters on every line to say one bit of information.
 */
function venue(fixtures: readonly string[]): string {
  if (fixtures.length === 0) return "—";
  return fixtures
    .map((fixture) => {
      const [club, side] = fixture.split(" ");
      if (!club) return fixture;
      return side === "(H)" ? club.toUpperCase() : club.toLowerCase();
    })
    .join(" ");
}

function TeamSheet({
  benchCounts,
  onOpen,
  week,
}: {
  benchCounts: boolean;
  onOpen: (player: PlanPlayer) => void;
  week: PlanGameweek;
}) {
  const role = (player: PlanPlayer) => {
    if (player.code === week.captain.code) return "C";
    if (player.code === week.viceCaptain.code) return "V";
    return null;
  };

  const line = (player: PlanPlayer, benched: boolean) => {
    const badge = role(player);
    const captain = player.code === week.captain.code;
    const raw = week.expected[String(player.code)] ?? 0;
    const peak = week.ceiling[String(player.code)] ?? raw;
    // The armband doubles the score, so the line shows what he actually returns.
    const points = captain ? raw * 2 : raw;
    const best = captain ? peak * 2 : peak;
    const scores = !benched || benchCounts;
    const rating = week.difficulty[player.club] ?? null;
    const fixtureEvidence = week.fixtureEvidence[player.club]?.[0];

    return (
      <li key={player.code}>
        <Shirt club={player.club} />
        <span className="plan-name">
          <button
            className="plan-open"
            onClick={() => {
              onOpen(player);
            }}
            type="button"
          >
            {player.name}
            {badge ? ` (${badge})` : ""}
          </button>
        </span>
        <span className="plan-price mono">
          {money.format(player.priceTenths / 10)}
        </span>
        <span className="plan-against mono">
          {venue(week.opponents[player.club] ?? [])}
        </span>
        <span
          className={`plan-fdr mono plan-fdr-${rating === null ? "none" : String(Math.round(rating))}`}
          title={
            rating === null
              ? "No fixture, or no measured record for this club"
              : fixtureEvidence
                ? `Team-relative matchup ${rating.toFixed(1)} of 5${fixtureEvidence.difficulty.clipped ? `; raw ${fixtureEvidence.difficulty.raw?.toFixed(1) ?? "unknown"} was bounded` : ""}`
                : `Team-relative matchup ${rating.toFixed(1)} of 5`
          }
        >
          {rating === null ? "\u2014" : rating.toFixed(1)}
        </span>
        <span
          className={
            captain
              ? "plan-points mono plan-points-captain"
              : "plan-points mono"
          }
        >
          {scores ? points.toFixed(1) : `(${points.toFixed(1)})`}
        </span>
        <span
          className="plan-ceiling mono"
          title="What the same match is worth on his best afternoon"
        >
          {scores ? best.toFixed(1) : `(${best.toFixed(1)})`}
        </span>
      </li>
    );
  };

  return (
    <div className="plan-sheet">
      <p className="plan-sheet-head mono" aria-hidden="true">
        <span />
        <span>Player</span>
        <span>£</span>
        <span>Opp</span>
        <span>Match</span>
        <span>xPts</span>
        <span>xCeil</span>
      </p>
      <ol className="plan-eleven">
        {week.starters.map((player) => line(player, false))}
      </ol>
      <ol className="plan-bench" aria-label="Bench in order">
        {week.bench.map((player) => line(player, true))}
      </ol>
    </div>
  );
}

function oneDecimal(value: number): string {
  return `${value < 0 ? "−" : ""}${Math.abs(value).toFixed(1)}`;
}

export function FixtureEvidenceList({
  evidence,
}: {
  evidence: Readonly<Record<string, readonly FixtureEvidence[]>>;
}) {
  const rows = Object.entries(evidence).flatMap(([club, fixtures]) =>
    fixtures.map((fixture) => ({ club, fixture })),
  );
  if (rows.length === 0) return null;

  return (
    <div className="plan-fixture-evidence">
      <ul>
        {rows.map(({ club, fixture }) => (
          <li key={`${club}-${String(fixture.event)}-${fixture.opponent}`}>
            <strong>
              {club} v {fixture.opponent} ({fixture.venue})
            </strong>
            <span className="mono">
              {fixture.expectedGoals.toFixed(2)} xG ·{" "}
              {fixture.opponentExpectedGoals.toFixed(2)} xGA ·{" "}
              {(fixture.cleanSheetProbability * 100).toFixed(1)}% clean sheet
            </span>
            <span className="mono">
              Attack {fixture.adjustments.attacking.toFixed(3)}× · Defence{" "}
              {fixture.adjustments.cleanSheet.toFixed(3)}× · Conceding{" "}
              {fixture.adjustments.conceding.toFixed(3)}× · Saves{" "}
              {fixture.adjustments.saves.toFixed(3)}× · DefCon{" "}
              {fixture.adjustments.defensiveContribution.toFixed(3)}×
            </span>
            <span className="plan-fixture-summary mono">
              {fixture.difficulty.clipped
                ? `Matchup raw ${fixture.difficulty.raw === null ? "unknown" : oneDecimal(fixture.difficulty.raw)}, bounded to ${fixture.difficulty.summary?.toFixed(1) ?? "unknown"}.`
                : `Matchup ${fixture.difficulty.summary?.toFixed(1) ?? "unavailable"}/5 from attack divided by expected conceding.`}
            </span>
            <span className="plan-fixture-source">
              {fixture.level} · {fixture.source} ·{" "}
              {fixture.updatedAt === null
                ? "timestamp unavailable"
                : timestamp.format(new Date(fixture.updatedAt))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Move({ week }: { week: PlanGameweek }) {
  if (week.transfersIn.length === 0) {
    return (
      <p className="plan-move plan-move-roll">
        <span className="mono">
          {week.event === 1 ? "Opening squad" : "Roll the free transfer"}
        </span>
      </p>
    );
  }

  return (
    <>
      {week.chip ? (
        <p className="plan-move-chip mono">
          {week.chip} · {week.transfersIn.length}{" "}
          {week.chip === "Free Hit"
            ? "temporary changes"
            : week.chip === "Wildcard"
              ? "permanent changes"
              : "changes"}
        </p>
      ) : null}
      <ul className="plan-move">
        {pairTransfers(week.transfersOut, week.transfersIn).map((swap) => (
          <li key={swap.in.code}>
            <Shirt club={swap.out.club} />
            <span className="plan-out">{swap.out.name}</span>
            <ArrowRight aria-label="replaced by" size={15} />
            <Shirt club={swap.in.club} />
            <span className="plan-in">{swap.in.name}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function Why({ week, chip }: { week: PlanGameweek; chip: ChipCall | null }) {
  const fixtures = fixtureReason(week);
  const timing = deadlineAdvice(week);

  return (
    // Folded by default. Thirty-eight cards of open reasoning is a wall a
    // reader scrolls past rather than reads, and the squad and the haul are
    // what the card is for; this is the working behind them.
    <details className="plan-why-fold">
      <summary className="plan-why-summary">
        <span>Why</span>
      </summary>
      <dl className="plan-why">
        <dt data-label="move">Move</dt>
        <dd>
          <ul className="plan-money">
            {moveLines(week).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </dd>

        <dt data-label="money">Money</dt>
        <dd>
          <ul className="plan-money">
            {moneyLines(week).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </dd>

        {fixtures ? (
          <>
            <dt data-label="fixtures">Fixtures</dt>
            <dd>{fixtures}</dd>
          </>
        ) : null}

        {timing ? (
          <>
            <dt data-label="timing">Timing</dt>
            <dd>{timing}</dd>
          </>
        ) : null}

        <dt data-label="captain">Captain</dt>
        <dd>{captainLine(week)}</dd>

        {Object.keys(week.fixtureEvidence).length > 0 ? (
          <>
            <dt data-label="market">Market evidence</dt>
            <dd>
              <FixtureEvidenceList evidence={week.fixtureEvidence} />
            </dd>
          </>
        ) : null}

        <dt data-label="confidence">Confidence</dt>
        <dd>{confidenceReason(week)}</dd>

        <dt data-label="chip">Chip</dt>
        <dd>{chipReason(chip, week.chip !== undefined)}</dd>
      </dl>
    </details>
  );
}

function GameweekCard({
  chip,
  onOpen,
  week,
}: {
  chip: ChipCall | null;
  onOpen: (player: PlanPlayer) => void;
  week: PlanGameweek;
}) {
  const deadline = new Date(week.deadline);
  const boosted = chip?.chip === "Bench Boost";
  // Triple Captain adds a third copy, not a second. Counting it as an ordinary
  // armband understated the one week the chip is played by a whole captain.
  const armband = chip?.chip === "Triple Captain" ? 2 : 1;

  const sum = (
    players: readonly PlanPlayer[],
    from: Readonly<Record<string, number>>,
  ) =>
    players.reduce(
      (total, player) => total + (from[String(player.code)] ?? 0),
      0,
    );

  // What the card actually returns: the eleven, the armband again, and the
  // bench only when a boost is paying for it.
  const total = (from: Readonly<Record<string, number>>) =>
    sum(week.starters, from) +
    armband * (from[String(week.captain.code)] ?? 0) +
    (boosted ? sum(week.bench, from) : 0);

  const haul = total(week.expected);
  const captainExpected = week.expected[String(week.captain.code)] ?? 0;
  const viceExpected = week.expected[String(week.viceCaptain.code)] ?? 0;
  const captainGap = captainExpected - viceExpected;
  // Empty where the run that produced this week could not measure a spread.
  const ceiling =
    Object.keys(week.ceiling).length > 0 ? total(week.ceiling) : null;

  return (
    <li className={`plan-card plan-${week.confidence}`}>
      <div className="plan-card-head">
        <span className="plan-gw mono">GW{week.event}</span>
        <span className="plan-date mono">{deadlineDay.format(deadline)}</span>
        {chip ? (
          <span className="plan-chip mono">
            {chip.chip}
            {week.chip === undefined ? " advised" : ""}
          </span>
        ) : null}
      </div>

      <Move week={week} />
      <TeamSheet benchCounts={boosted} onOpen={onOpen} week={week} />

      <p className="plan-haul mono">
        EXPECTED HAUL {haul.toFixed(1)}
        {week.transferCostPoints > 0
          ? ` − ${week.transferCostPoints} hit = ${(haul - week.transferCostPoints).toFixed(1)}`
          : null}
        {ceiling === null ? null : (
          <>
            <br />
            COMBINED CEILING {ceiling.toFixed(1)}
          </>
        )}
      </p>

      <p className="plan-captain-note mono">
        CAPTAIN {week.captain.name} {captainExpected.toFixed(1)} · VICE{" "}
        {week.viceCaptain.name} {viceExpected.toFixed(1)} · GAP{" "}
        {captainGap.toFixed(1)}
      </p>

      <Why chip={chip} week={week} />
    </li>
  );
}

/** The solved shape carries everything the published one does, plus ids. */
function asPlanGameweek(week: SolvedGameweek): PlanGameweek {
  return {
    event: week.event,
    deadline: week.deadline,
    confidence: week.confidence,
    starters: week.starters,
    bench: week.bench,
    captain: week.captain,
    viceCaptain: week.viceCaptain,
    transfersIn: week.transfersIn,
    transfersOut: week.transfersOut,
    opponents: week.opponents,
    difficulty: week.difficulty,
    fixtureEvidence: fixtureEvidenceForClubs(
      [...week.starters, ...week.bench].map((player) => player.club),
      week.event,
    ),
    expected: week.expected,
    // The solver returns a mean and no spread. Copying the mean in here was a
    // ceiling that always equalled the expectation, which reads as a measured
    // claim that the week has no upside. Empty means unmeasured, and the card
    // prints nothing rather than a number that is really the mean again.
    ceiling: {},
    chip: week.chip,
    revertsAfter: week.revertsAfter,
    revertsTo: week.revertsTo,
    freeTransfersBefore: week.freeTransfersBefore,
    paidTransfers: week.paidTransfers,
    transferCostPoints: week.transferCostPoints,
    projectedPoints: week.projectedPoints,
    netExpectedPoints: week.netExpectedPoints,
    bankAfterTenths: week.bankAfterTenths,
  };
}

/**
 * All eight chips at once, because they are a season-long budget rather than
 * eight separate decisions. FPL hands the set out twice: whatever is unplayed
 * by gameweek nineteen expires, and a fresh set arrives for the second half.
 */
function ChipStrategy({ chips }: { chips: readonly ChipCall[] }) {
  if (chips.length === 0) return null;
  const halves = [
    ["first", "First half, gameweeks 1 to 19"],
    ["second", "Second half, gameweeks 20 to 38"],
  ] as const;

  return (
    <div className="plan-chips">
      {halves.map(([half, label]) => (
        <div className="plan-chip-half" key={half}>
          <h3>{label}</h3>
          <ul>
            {chips
              .filter((chip) => chip.half === half)
              .map((chip) => (
                <li key={`${chip.chip}-${half}`}>
                  <span className="plan-chip-when mono">
                    {chip.event === null ? "—" : `GW${String(chip.event)}`}
                  </span>
                  <span className="plan-chip-name">{chip.chip}</span>
                  <span
                    className={
                      chip.gain >= CHIP_TARGET
                        ? "plan-chip-gain mono plan-chip-hit"
                        : "plan-chip-gain mono"
                    }
                  >
                    +{chip.gain.toFixed(1)}
                  </span>
                  <span className="plan-chip-note">{chip.note}.</span>
                  {chip.incoming && chip.incoming.length > 0 ? (
                    <span className="plan-chip-rebuild mono">
                      <span>
                        <strong>In</strong> {chip.incoming.join(", ")}
                      </span>
                      <span>
                        <strong>Out</strong> {chip.outgoing?.join(", ") ?? "—"}
                      </span>
                    </span>
                  ) : null}
                </li>
              ))}
          </ul>
        </div>
      ))}
      <p className="plan-chip-footnote">
        The figure is what playing the chip that week adds over not playing it,
        not what the week scores. Anything left unplayed by gameweek nineteen
        expires rather than carrying over.
      </p>
    </div>
  );
}

/**
 * What the columns on a gameweek card mean.
 *
 * It sat in the page preamble, two disclosures away from the only thing it
 * describes, so it was read before there was anything to read it against.
 */
function ReadingKey() {
  return (
    <dl className="plan-key">
      <div>
        <dt>xPts</dt>
        <dd>
          Expected points from one match. Four to six is a good starter, seven
          and up is a strong fixture.
          <InfoMarker label="xPts">
            Appearance, goals and assists at his own decayed per-90 rates, plus
            clean sheets, saves, cards and defensive contribution, all scaled by
            this opponent.
          </InfoMarker>
        </dd>
      </div>
      <div>
        <dt>xCeil</dt>
        <dd>
          The same match on his best afternoon. What an armband or a chip is
          played for.
          <InfoMarker label="xCeil">
            xPts multiplied by how far his ninetieth-percentile score sat above
            his average last season. A centre-half who plays ninety and does
            nothing lands near twice his xPts; a striker who either scores or
            vanishes nearer three times it.
          </InfoMarker>
        </dd>
      </div>
      <div>
        <dt>Match</dt>
        <dd>
          Team-relative matchup difficulty. One is softest, five hardest, a dash
          is a blank.
          <InfoMarker label="matchup difficulty">
            This is the opponent&rsquo;s attacking strength over its defensive
            tightness at the venue, mapped to one-to-five. The same opponent at
            the same venue therefore keeps the same rating whoever faces it.
            Route-specific xPts still uses both teams, because Arsenal and
            Brentford should not project the same score against Chelsea.
          </InfoMarker>
        </dd>
      </div>
      <div>
        <dt>Opponent</dt>
        <dd>
          Capitals are home, lower case away. <span className="mono">HUL</span>{" "}
          is at home to Hull; <span className="mono">hul</span> is away at Hull.
        </dd>
      </div>
      <div>
        <dt>Captain</dt>
        <dd>
          Shown <strong>doubled</strong>. Bench figures are bracketed unless a
          Bench Boost is paying for them.
          <InfoMarker label="the armband rule">
            The captain is the highest expected score, and {CAPTAINCY_VERDICT}{" "}
            Every card names the runner-up so the call is arguable rather than
            asserted.
          </InfoMarker>
        </dd>
      </div>
      <div>
        <dt>Hard ties</dt>
        <dd>
          Kept, not avoided.
          <InfoMarker label="why hard fixtures stay">
            The projection already prices the opponent in, so a four-rated tie
            is a lower xPts rather than a reason to sell. Selling a good player
            for one hard week costs more than the week does.
          </InfoMarker>
        </dd>
      </div>
    </dl>
  );
}

export default function SeasonPlanPage() {
  const plan = useMemo(() => readSeasonPlan(), []);
  const [selected, setSelected] = useState<{
    player: PlanPlayer;
    week: PlanGameweek;
  } | null>(null);
  const [params, setParams] = useSearchParams();
  // Nobody reads thirty-eight cards at once, and drawing them all on mount is
  // heavy enough that the page could not share a render with anything else.
  const [shownWeeks, setShownWeeks] = useState(INITIAL_WEEKS);
  const [openingEdit, setOpeningEdit] = useState<{
    entryId: number;
    decision: OpeningDecision;
  } | null>(null);
  const railEnd = useRef<HTMLParagraphElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  // Bumped when a transfer is declared, so the squad is read again with it.
  const [declaredAt, setDeclaredAt] = useState(0);
  const [chosenObjective, setChosenObjective] = useState<RankObjective | null>(
    null,
  );
  // Held beside the stored value rather than replacing it, and stamped with the
  // team it belongs to, so switching id cannot inherit the last one's chips.
  const [chipEdit, setChipEdit] = useState<{
    entryId: number;
    chips: DeclaredChips;
  } | null>(null);
  /*
   * Nothing to solve until a manager has a squad. Between seasons FPL wipes
   * them all, so the published plan really is everyone's plan — it is what
   * Andres thinks the optimal opening squad does with the whole season. From
   * the first deadline it stops being true for anybody, and the solve below
   * takes over.
   */
  const fromEvent = Number(params.get("from") ?? "");
  // The URL wins, then the browser's memory of the last team. A seven-digit
  // Team ID is not something anybody memorises, and asking for it again on
  // every visit is the first friction a returning reader meets.
  const teamParam =
    params.get("team") ?? readLastTeam(window.localStorage)?.toString() ?? null;
  const teamId =
    teamParam !== null && /^\d+$/.test(teamParam) ? Number(teamParam) : null;
  const planningEvent = currentPlanningEvent();
  const openingDecision =
    teamId === null || planningEvent !== PRE_SEASON_EVENT
      ? null
      : openingEdit?.entryId === teamId
        ? openingEdit.decision
        : (readDeclaredSquad(window.localStorage, teamId, PRE_SEASON_EVENT)
            ?.openingDecision ?? null);
  /*
   * A declared fifteen carried in the link.
   *
   * Mobile Safari clears script-written storage after a week without a visit,
   * so a manager coming back to check his plan found his squad gone. A
   * bookmark is not script-written storage. `useTeamPlan` reads it, because the
   * squad is only read once FPL has answered and a restore here would race
   * that. It never overwrites a squad this browser already holds.
   */
  const squadParam = params.get("squad");

  /**
   * Keep the address bar carrying whatever fifteen is stored.
   *
   * Idempotent and self-terminating: it compares against the code already in
   * the URL and does nothing when they agree. Replaces rather than pushes —
   * this is the page you are on, not one you navigated to.
   */
  useEffect(() => {
    if (teamId === null) return;
    const stored = readDeclaredSquad(
      window.localStorage,
      teamId,
      planningEvent,
    );
    const code = stored ? encodeSquad(stored.elementIds) : null;
    if (code === squadParam) return;
    // Nothing declared in this session yet, so empty storage means the link has
    // not been read rather than that the squad was cleared. Removing the code
    // here would throw away the only copy on the way to restoring it.
    if (code === null && declaredAt === 0) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("team", String(teamId));
        if (code) next.set("squad", code);
        else next.delete("squad");
        return next;
      },
      { replace: true },
    );
  }, [declaredAt, planningEvent, squadParam, setParams, teamId]);
  const teamPlan = useTeamPlan(teamParam, declaredAt, squadParam);
  const team = teamPlan.start;

  // Remembered once FPL has actually answered for it, so a mistyped number
  // never becomes the id this browser offers next time.
  useEffect(() => {
    if (teamId !== null && team.status === "ready") {
      rememberTeam(window.localStorage, teamId);
    }
  }, [teamId, team.status]);

  /*
   * Settle the call made for the gameweek FPL has now published.
   *
   * The published fifteen is what he actually fielded, so his transfer is the
   * difference between it and the fifteen the advice was given from. Nothing is
   * settled twice, so a later visit cannot rewrite a result.
   */
  const published =
    teamPlan.analysis.status === "ready" ||
    teamPlan.analysis.status === "stale" ||
    teamPlan.analysis.status === "refreshing"
      ? teamPlan.analysis.state
      : null;

  const declaredChips = useMemo(() => {
    if (teamId === null) return NO_CHIPS;
    return chipEdit?.entryId === teamId
      ? chipEdit.chips
      : readDeclaredChips(window.localStorage, teamId);
  }, [chipEdit, teamId]);

  // Held beside the stored answer and stamped with the team it belongs to, so
  // switching id cannot inherit the last one's league.
  const objective = useMemo(() => {
    if (teamId === null) return null;
    return chosenObjective ?? readRankObjective(window.localStorage, teamId);
  }, [chosenObjective, teamId]);

  const live = useMemo(() => {
    // His own fifteen beats a gameweek number, because it is his season either
    // way and only one of the two knows what he owns.
    const base =
      team.status === "ready"
        ? team.start
        : Number.isInteger(fromEvent) && fromEvent >= 1 && fromEvent <= 38
          ? (() => {
              const opening = plan.gameweeks[0];
              return opening
                ? startFromCodes(
                    [...opening.starters, ...opening.bench].map(
                      (player) => player.code,
                    ),
                    { bankTenths: 0, availableFreeTransfers: 1, fromEvent },
                  )
                : null;
            })()
          : null;
    if (!base) return null;
    // A committed wildcard is the one declaration that changes the solve
    // itself: it ends the run every player before it is being valued over.
    const committed = declaredChips.committed;
    const rebuild =
      committed?.chip === "wildcard" ? { rebuildAtEvent: committed.event } : {};
    const freeHit =
      committed?.chip === "freehit" ? { freeHitAtEvent: committed.event } : {};
    return openingDecision
      ? { ...base, ...rebuild, ...freeHit, lockOpening: true }
      : { ...base, ...rebuild, ...freeHit };
  }, [declaredChips, fromEvent, openingDecision, plan.gameweeks, team]);

  const spentChips = useMemo(
    () =>
      declaredChips.spent.map(
        ({ chip, half }) => `${CHIP_NAMES[chip]}:${half}`,
      ),
    [declaredChips],
  );
  const committedChip = useMemo(
    () =>
      declaredChips.committed
        ? {
            chip: CHIP_NAMES[declaredChips.committed.chip],
            event: declaredChips.committed.event,
          }
        : null,
    [declaredChips],
  );
  const baselineSolve = useSeasonSolve(live);
  const baselineChipCalls = useMemo(
    () =>
      live !== null && baselineSolve.status === "done"
        ? chipCallsFor(
            baselineSolve.gameweeks,
            plan.chips,
            spentChips,
            committedChip,
          )
        : chipCallsFor([], plan.chips, spentChips, committedChip),
    [
      live,
      baselineSolve.status,
      baselineSolve.gameweeks,
      plan.chips,
      spentChips,
      committedChip,
    ],
  );
  const rebuilds = useMemo(
    () => plannedRebuilds(baselineChipCalls),
    [baselineChipCalls],
  );
  const plannedLive = useMemo(() => {
    if (live === null || baselineSolve.status !== "done") return null;
    if (
      rebuilds.freeHitPlans.length === 0 &&
      rebuilds.wildcardPlans.length === 0
    ) {
      return null;
    }
    return {
      ...live,
      freeHitPlans: rebuilds.freeHitPlans,
      wildcardPlans: rebuilds.wildcardPlans,
    };
  }, [baselineSolve.status, live, rebuilds]);
  const plannedSolve = useSeasonSolve(plannedLive);
  const solve = plannedLive === null ? baselineSolve : plannedSolve;
  const solving = live !== null;

  /*
   * The record of what was advised against what was done.
   *
   * Both halves are written here rather than in an effect, so the table below
   * is never a render behind the week that just settled. Safe to do while
   * rendering because both writes refuse to overwrite: a call is recorded once
   * per gameweek and a result is settled once, so running twice under Strict
   * Mode changes nothing. That is a property of `scorecard.ts`, not a hope —
   * it is the same property that stops a re-solve rewriting yesterday's advice.
   */
  const scorecard = useMemo(() => {
    if (teamId === null) return [];
    const captain = published?.picks.find((pick) => pick.isCaptain);
    if (published && captain) {
      settleCall(
        window.localStorage,
        teamId,
        published.event,
        published.picks.map((pick) => pick.elementId),
        captain.elementId,
      );
    }
    const next = solve.status === "done" ? solve.gameweeks[0] : null;
    if (
      next &&
      next.chip === undefined &&
      team.status === "ready" &&
      team.source === "published"
    ) {
      recordCall(window.localStorage, teamId, {
        event: next.event,
        squadBefore: team.start.squad.map((held) => held.elementId),
        elementOut: next.transfersOut[0]?.id ?? null,
        elementIn: next.transfersIn[0]?.id ?? null,
        captain: next.captain.id,
      });
    }
    return readScorecard(window.localStorage, teamId);
  }, [published, solve.gameweeks, solve.status, team, teamId]);

  // Rebuild chips stay on the baseline that selected their exact legal squad.
  // Bench Boost and Triple Captain are then repriced from the chip-aware plan.
  const postChipCalls = useMemo(
    () =>
      solving && solve.status === "done"
        ? chipCallsFor(solve.gameweeks, plan.chips, spentChips, committedChip)
        : baselineChipCalls,
    [
      solving,
      solve.status,
      solve.gameweeks,
      plan.chips,
      spentChips,
      committedChip,
      baselineChipCalls,
    ],
  );
  const chipCalls = useMemo(() => {
    if (plannedLive === null || solve.status !== "done") {
      return baselineChipCalls;
    }
    const postByChip = new Map(
      postChipCalls.map((call) => [`${call.chip}:${call.half}`, call]),
    );
    return resolveChipClashes(
      baselineChipCalls.map((call) =>
        call.chip === "Free Hit" || call.chip === "Wildcard"
          ? call
          : (postByChip.get(`${call.chip}:${call.half}`) ?? call),
      ),
      committedChip,
    );
  }, [
    baselineChipCalls,
    committedChip,
    plannedLive,
    postChipCalls,
    solve.status,
  ]);
  // Someone who has given a team id is here for their own season. Showing the
  // published optimum until they lock a fifteen in reads as "here is your
  // plan" when it is nobody's, and removes any reason to declare a squad.
  const awaitingLockIn =
    teamId !== null &&
    team.status === "failed" &&
    team.reason === "no_processed_event";
  // Wildcard and Free Hit still belong to the published fifteen even once the
  // other two have been re-solved, and the panel says so rather than implying
  // all eight half-season copies are his.
  const chipsAreYours =
    !awaitingLockIn && (!solving || solve.status === "done");
  const gameweeks = solving
    ? solve.gameweeks.map(asPlanGameweek)
    : plan.gameweeks;
  const chips = useMemo(() => {
    return chipCallsByEvent(chipCalls, gameweeks, committedChip);
  }, [chipCalls, gameweeks, committedChip]);

  // Only gameweek one, and only when it is the reader's own squad being
  // solved: past the first deadline a change is a transfer and costs points.
  const openingChanges = useMemo(() => {
    const opener = gameweeks[0];
    if (!solving || opener?.event !== 1) return [];
    return opener.transfersIn.map((incoming, index) => ({
      incoming,
      outgoing: opener.transfersOut[index],
    }));
  }, [gameweeks, solving]);

  const decideOpening = (decision: OpeningDecision) => {
    if (teamId === null || live === null) return;
    const opener = solve.gameweeks[0];
    if (opener?.event !== PRE_SEASON_EVENT) return;
    const elementIds =
      decision === "accepted"
        ? [...opener.starters, ...opener.bench].map((player) => player.id)
        : live.squad.map((player) => player.elementId);
    saveDeclaredSquad(
      window.localStorage,
      teamId,
      PRE_SEASON_EVENT,
      elementIds,
      PLAYERS_BY_ELEMENT_ID,
      () => new Date(),
      { openingDecision: decision },
    );
    setOpeningEdit({ entryId: teamId, decision });
    setDeclaredAt(Date.now());
  };

  // Reaching the end of the rail asks for more of it. The button below stays,
  // because scrolling is not a control and a keyboard has nothing to scroll to.
  useEffect(() => {
    const node = railEnd.current;
    if (!node || typeof IntersectionObserver === "undefined") return;

    const watcher = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShownWeeks((shown) => shown + INITIAL_WEEKS);
        }
      },
      { rootMargin: "400px" },
    );
    watcher.observe(node);
    return () => {
      watcher.disconnect();
    };
  }, [shownWeeks, gameweeks.length]);

  useDocumentTitle(
    // A page about one manager's season says whose. The team view folded into
    // this route and the title stopped naming the team with it, so a tab, a
    // bookmark and a shared link all read as the generic plan.
    teamId === null ? "The season plan" : `Team ${String(teamId)}`,
    "Every gameweek from 1 to 38: squad, eleven, captain and transfer, with " +
      "confidence that falls away the further out it reaches.",
    { canonicalPath: "/plan" },
  );

  const bands = useMemo(() => {
    const counted = new Map<Confidence, number>();
    for (const week of gameweeks) {
      counted.set(week.confidence, (counted.get(week.confidence) ?? 0) + 1);
    }
    return counted;
  }, [gameweeks]);

  // The costliest name in the whole pool the plan never fields. Read off the
  // pool rather than the squad: "bought and benched" is a much weaker claim
  // than "never bought at all", and the second is the one worth defending.
  const absentPremium = useMemo(() => {
    const started = new Set<number>();
    for (const week of gameweeks) {
      for (const player of week.starters) started.add(player.code);
    }
    return [...PLAYERS_BY_ELEMENT_ID.values()]
      .filter((player) => !started.has(player.code))
      .sort((left, right) => right.priceTenths - left.priceTenths)[0];
  }, [gameweeks]);

  return (
    <section className="season-plan" aria-label="The season plan">
      <div className="section-index" aria-hidden="true">
        02 / THE SEASON
      </div>

      <RouteHeading>Season Plan</RouteHeading>

      {/* One page, one subject. The snapshot, the record and the fifteen used
          to be a separate route, which is what made a locked-in squad look
          ignored by the plan. `useTeamPlan` already asked FPL, so nothing here
          fetches again — that endpoint is rate limited. */}
      <PlanStep
        note={
          teamId === null
            ? "enter your Team ID"
            : teamId.toLocaleString("en-GB")
        }
        step="01"
        title="Your manager and season"
      >
        <TeamEntry team={team} params={params} onChange={setParams} />
        {teamId === null ? null : (
          <>
            <DeclaredSquadNote entryId={teamId} />
            <div
              aria-label="Analysis result"
              className="analysis-result"
              key={teamId}
              ref={resultRef}
              role="region"
              tabIndex={-1}
            >
              <AnalysisResult
                analysis={teamPlan.analysis}
                declaredAt={declaredAt}
                entryId={teamId}
                onDeclared={() => {
                  setOpeningEdit(null);
                  setDeclaredAt(Date.now());
                }}
                onRetry={() => {
                  // Focus moves to the region so a screen reader hears the
                  // retry's answer rather than being left on a button that
                  // vanished.
                  resultRef.current?.focus();
                  teamPlan.retry();
                }}
              />
            </div>
            {/* Announces the transition only. Marking the plan live would
                re-read every gameweek card each time the squad resolved. */}
            <p aria-live="polite" className="visually-hidden" role="status">
              {analysisAnnouncement(teamPlan.analysis, teamId)}
            </p>
          </>
        )}
      </PlanStep>

      {teamId === null ? null : (
        <PlanStep
          note={published ? `GW${String(published.event)}` : "awaiting scores"}
          step="02"
          title="Last gameweek"
        >
          <Scorecard calls={scorecard} />
          {published === null ? null : (
            <>
              {published.event === GW1_REVIEW_EVENT &&
              teamId === GW1_REVIEW_ENTRY_ID ? (
                <Suspense
                  fallback={<p className="mono">Loading frozen review…</p>}
                >
                  <Gw1ReviewPitch />
                </Suspense>
              ) : (
                <LiveSquad event={published.event} picks={published.picks} />
              )}
            </>
          )}
        </PlanStep>
      )}

      {teamId === null ? null : (
        <PlanStep
          note={objective ? "objective set" : "answer before solving"}
          step="03"
          title="Set your plan"
        >
          <p className="plan-inputs-intro">
            Set your race, any post-deadline transfers and chip state. Each
            answer re-solves the plan.
          </p>
          <RankObjectiveForm entryId={teamId} onChosen={setChosenObjective} />
          {team.status === "ready" && team.source === "published" ? (
            <DeclaredTransferForm
              entryId={teamId}
              event={team.event}
              season={plan.season}
              onDeclared={() => {
                setDeclaredAt(Date.now());
              }}
            />
          ) : null}
          <DeclaredChipsForm
            entryId={teamId}
            onDeclared={(chips) => {
              setChipEdit({ entryId: teamId, chips });
            }}
          />
          {chasesLeague(objective) ? (
            published === null ? (
              <section aria-labelledby="mini-league" className="mini-league">
                <h2 id="mini-league">Your league</h2>
                <p className="mini-league-failed" role="status">
                  FPL keeps every squad private until a deadline has passed, so
                  there is nothing in your league to read yet. This fills in
                  after this entry has a processed deadline.
                </p>
              </section>
            ) : (
              <MiniLeagueThreats
                entryId={teamId}
                event={published.event}
                leagueId={objective.leagueId}
                mine={published.picks
                  .filter((pick) => pick.multiplier > 0)
                  .map((pick) => pick.elementId)}
              />
            )
          ) : null}
        </PlanStep>
      )}

      <PlanStep
        note={
          awaitingLockIn
            ? "waiting on your fifteen"
            : `GW${String(gameweeks[0]?.event ?? 1)}–${String(gameweeks[gameweeks.length - 1]?.event ?? 38)}`
        }
        step="04"
        title="Your plan"
      >
        <section aria-labelledby="chip-plan-title" className="plan-subsection">
          <h2 id="chip-plan-title">Chip strategy</h2>
          {chipsAreYours ? (
            <>
              {solving ? (
                <p className="plan-chip-scope">
                  All eight chip copies solved from <strong>your</strong> squad.
                  <InfoMarker label="how each chip is priced">
                    Bench Boost pays what your bench scores and Triple Captain
                    pays what your captain scores, both read off the weeks
                    below. Wildcard and Free Hit are first priced by rebuilding
                    your fifteen from the whole pool at every week. Their exact
                    legal squads are then applied in a second full-season solve,
                    so the gameweeks below include the chip and everything that
                    follows it.
                  </InfoMarker>
                </p>
              ) : null}
              <ChipStrategy chips={chipCalls} />
            </>
          ) : (
            <p className="plan-awaiting">
              A chip is only worth what your squad makes of it.{" "}
              {awaitingLockIn
                ? "State your squad above and the chip weeks are solved from your bench and captain."
                : "Solving yours now."}
            </p>
          )}
        </section>

        <section
          aria-labelledby="gameweek-plan-title"
          className="plan-subsection"
        >
          <h2 id="gameweek-plan-title">Every gameweek</h2>
          <div className="plan-preamble">
            <p className="plan-preamble-line">
              Squad, eleven, captain and transfer, for every gameweek. Solved in
              your browser.
              <InfoMarker label="how this plan is built">
                {awaitingLockIn
                  ? `A plan is only worth reading if it starts from what you own. Lock a fifteen in at step one and all 38 gameweeks are solved from it here, in ${String(plan.windowsSolved)} overlapping windows from a pool of ${String(plan.poolSize)} players.`
                  : `A single optimal 38-gameweek solve does not return, so this is ${String(plan.windowsSolved)} overlapping windows chained together from a pool of ${String(plan.poolSize)} players. A good plan, not a proof. Your squad, bank and free transfers never leave this browser.`}
              </InfoMarker>
            </p>
            <ul className="plan-preamble-stats mono">
              <li>
                <b>
                  {awaitingLockIn
                    ? `GW${String(planningEvent)}–38`
                    : `GW${String(gameweeks[0]?.event)}–${String(gameweeks[gameweeks.length - 1]?.event)}`}
                </b>{" "}
                planned
              </li>
              {solving || awaitingLockIn ? null : (
                <li>
                  <b>{plan.netExpectedPoints.toFixed(0)}</b> net points
                </li>
              )}
              {solving || awaitingLockIn ? null : (
                <li>
                  <b>{bands.get("firm") ?? 0}</b> firm ·{" "}
                  <b>{bands.get("projected") ?? 0}</b> projected ·{" "}
                  <b>{bands.get("provisional") ?? 0}</b> provisional
                  <InfoMarker label="firm, projected and provisional">
                    Firm means the gameweek already happened, so every number is
                    observed. Projected sits inside the seven-gameweek horizon
                    the model is calibrated on. Provisional is beyond it — read
                    the shape, not the names.
                  </InfoMarker>
                </li>
              )}
              {awaitingLockIn ? <li>no squad locked in yet</li> : null}
            </ul>
          </div>

          {solve.status === "solving" ? (
            <p className="plan-progress" role="status">
              <span
                aria-hidden="true"
                className="plan-progress-bar"
                style={{
                  inlineSize: `${Math.round((solve.progress ?? 0) * 100)}%`,
                }}
              />
              Solved {solve.gameweeks.length} of {38 - fromEvent + 1} gameweeks…
            </p>
          ) : null}

          {solve.status === "failed" ? (
            <p className="plan-progress plan-progress-failed" role="alert">
              The solver stopped: {solve.reason}. The published opening-squad
              plan is still below.
            </p>
          ) : null}

          {awaitingLockIn ? (
            <p className="plan-awaiting">
              Lock a fifteen in at step one and all thirty-eight weeks are
              re-solved from it. Until then this is not your plan.
            </p>
          ) : (
            <>
              {live && live.assumed.length > 0 ? (
                <p className="plan-assumed" role="status">
                  <strong>Private state FPL will not tell me.</strong>{" "}
                  {live.assumed.includes("bank") ? "Bank — assumed zero. " : ""}
                  {live.assumed.includes("free_transfers")
                    ? "Free transfers held \u2014 assumed one. "
                    : ""}
                  {live.assumed.includes("selling_prices")
                    ? "What you paid, so risers are priced at today's list. "
                    : ""}
                  Correct them in step one.
                  <InfoMarker label="the private planning numbers">
                    These are private to your account, so no public endpoint
                    carries them. A selling price is buy price plus half the
                    rise, which changes what a transfer can afford. Correcting
                    any of them re-solves the whole season on the real numbers.
                  </InfoMarker>
                </p>
              ) : null}
              <ReadingKey />
              {openingChanges.length > 0 || openingDecision ? (
                <div className="plan-opening-advice">
                  <p>
                    {openingDecision ? (
                      <>
                        <strong>
                          {openingDecision === "accepted"
                            ? "Using the recommended fifteen."
                            : "Keeping your fifteen."}
                        </strong>{" "}
                        Gameweek 1 is locked, saved in this browser, and the
                        season is solved from there.
                      </>
                    ) : (
                      <>
                        <strong>
                          {openingChanges.length}{" "}
                          {openingChanges.length === 1 ? "change" : "changes"}{" "}
                          before the deadline, free.
                        </strong>{" "}
                        Nothing is charged for these &mdash; the squad is still
                        being picked.
                        <InfoMarker label="free pre-deadline changes">
                          FPL only starts charging for transfers once the first
                          deadline has passed. Until then a squad can be edited
                          as often as you like, so these are advice rather than
                          a hit.
                        </InfoMarker>
                      </>
                    )}
                  </p>
                  {openingDecision ? null : (
                    <ul className="plan-opening-list">
                      {openingChanges.map(({ incoming, outgoing }) => (
                        <li key={incoming.code}>
                          <span className="plan-out">
                            {outgoing?.name ?? "\u2014"}
                          </span>
                          <ArrowRight aria-label="replaced by" size={15} />
                          <span className="plan-in">{incoming.name}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="plan-opening-source">
                    FPL does not expose pre-deadline squads. Changes made only
                    on the FPL site cannot be detected automatically, so keep
                    the fifteen saved here in step one up to date.
                  </p>
                  {openingDecision ? null : (
                    <div className="plan-opening-actions">
                      <button
                        className="primary-command"
                        onClick={() => {
                          decideOpening("accepted");
                        }}
                        type="button"
                      >
                        Use these free changes
                      </button>
                      <button
                        className="secondary-command"
                        onClick={() => {
                          decideOpening("held");
                        }}
                        type="button"
                      >
                        Keep my fifteen
                      </button>
                    </div>
                  )}
                </div>
              ) : null}
              <ul className="plan-rail">
                {gameweeks.slice(0, shownWeeks).map((week) => (
                  <GameweekCard
                    chip={chips.get(week.event) ?? null}
                    key={week.event}
                    onOpen={(player) => {
                      setSelected({ player, week });
                    }}
                    week={week}
                  />
                ))}
              </ul>

              {shownWeeks < gameweeks.length ? (
                <p className="plan-more" ref={railEnd}>
                  <button
                    className="secondary-command"
                    onClick={() => {
                      setShownWeeks(gameweeks.length);
                    }}
                    type="button"
                  >
                    Show the remaining {String(gameweeks.length - shownWeeks)}{" "}
                    gameweeks
                  </button>
                </p>
              ) : null}

              {selected ? (
                <PlayerDetail
                  onClose={() => {
                    setSelected(null);
                  }}
                  player={selected.player}
                  difficulty={planDifficulty(selected.week, selected.player)}
                />
              ) : null}
            </>
          )}
        </section>

        <details className="plan-caveats-disclosure">
          <summary>
            What this plan cannot know · {String(CAVEAT_COUNT)} limits
          </summary>
          <section
            className="plan-caveats"
            aria-label="What this plan cannot know"
          >
            <ol>
              <li>
                <strong>Promoted clubs have no record.</strong>{" "}
                {plan.dataGaps.clubsInPool} of {plan.dataGaps.clubsInLeague}{" "}
                clubs are in the pool.
                <InfoMarker label="the missing clubs">
                  Every projection comes from {plan.recordSeason}, a season{" "}
                  {plan.dataGaps.clubsWithoutRecord.length > 0
                    ? `${plan.dataGaps.clubsWithoutRecord.join(" and ")} did not play in`
                    : "the promoted clubs did not play in"}
                  . Their players are missing from the pool entirely. Fixtures
                  against them use the named promoted-club prior because the
                  current FPL feed carries no usable club-strength fields and a
                  Premier League record does not exist yet.
                </InfoMarker>
              </li>
              <li>
                <strong>Prices are frozen at today&rsquo;s.</strong> A transfer
                eleven weeks out may be unaffordable by then.
                <InfoMarker label="price changes">
                  Players rise and fall all season and this plan holds
                  today&rsquo;s prices for all thirty-eight gameweeks. A squad
                  that banks value early can afford things this plan says it
                  cannot.
                </InfoMarker>
              </li>
              <li>
                <strong>No form, minutes or injuries yet.</strong> This is last
                season&rsquo;s record scaled by this season&rsquo;s fixtures.
                <InfoMarker label="what is not modelled">
                  A real plan moves week to week with form, minutes, injuries
                  and price changes, and against what your mini-league already
                  owns. None of that is in here.
                </InfoMarker>
              </li>
              <li>
                <strong>It will change every gameweek.</strong> Read the shape,
                not the names past the next month.
                <InfoMarker label="why the plan moves">
                  That is not a failure of the plan, it is what a plan is for.
                  The weeks worth a chip and the runs worth holding through
                  survive; individual names do not.
                </InfoMarker>
              </li>
              <li>
                <strong>New club arrivals wait one gameweek.</strong> A player
                FPL has just moved is not recommended immediately.
                <InfoMarker label="club assignment freshness">
                  Clubs are read from FPL&rsquo;s own player feed, not a
                  transfer rumour or an external news scrape. The planning
                  inputs compare each refresh with the previous assignment and
                  hold a moved player out through the next gameweek.
                </InfoMarker>
              </li>
              <li>
                <strong>
                  {absentPremium
                    ? `No ${absentPremium.name}, and that is the model talking.`
                    : "The expensive names are in on projection, not reputation."}
                </strong>{" "}
                {absentPremium ? (
                  <>
                    Points per pound, not doubt about the player.
                    <InfoMarker label="the missing premium">
                      He is the most expensive player in the game at{" "}
                      {money.format(absentPremium.priceTenths / 10)} and the
                      plan never fields him. A squad has £100.0m for fifteen, so
                      every extra million on one name is a million off the other
                      fourteen. He has to out-score not just the striker who
                      replaces him, but that striker plus the upgrades the
                      saving pays for everywhere else.
                    </InfoMarker>{" "}
                    Over four seasons nothing beat captaining the highest
                    projection, so the armband is not a separate reason to own
                    him &mdash;{" "}
                    <Link to="/calibration#captaincy-title">
                      the captaincy calibration
                    </Link>{" "}
                    closes that half of it.
                  </>
                ) : (
                  <>
                    Every player above the premium line for his position appears
                    in at least one eleven.
                  </>
                )}
              </li>
            </ol>
          </section>
          <p className="plan-basis mono">
            {plan.basis}. Records from {plan.recordSeason}. Transfer rules:{" "}
            {plan.rulesReference}.
          </p>
        </details>
      </PlanStep>
    </section>
  );
}
