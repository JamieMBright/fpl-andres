import { ArrowRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { CeefaxShirt } from "../components/CeefaxShirt";
import { PlayerDetail } from "../components/PlayerDetail";
import { RouteHeading } from "../components/RouteHeading";
import { deadlineDay, money } from "../format";
import { kitForShortName } from "../kit/team-kits";
import type { SolvedGameweek } from "../state/season-solver";
import { startFromCodes } from "../state/season-solver";
import { useSeasonSolve } from "../state/use-season-solve";
import type {
  TeamStartFailure,
  TeamStartStatus,
} from "../state/use-team-start";
import { useTeamStart } from "../state/use-team-start";
import type {
  ChipCall,
  Confidence,
  PlanGameweek,
  PlanPlayer,
} from "../state/season-plan";
import { readSeasonPlan } from "../state/season-plan";
import {
  chipReason,
  confidenceReason,
  fixtureReason,
  moneyLines,
  moveReason,
} from "../state/plan-reasons";
import { useDocumentTitle } from "../state/use-document-title";

/** What a chip should return before it is worth planning a season around. */
const CHIP_TARGET = 20;

const TEAM_FAILURE: Record<TeamStartFailure, string> = {
  not_a_team_id: "That is not a Team ID. It is the number in your FPL URL.",
  unreachable: "I could not reach FPL for that squad, so I am not guessing it.",
  no_processed_event:
    "FPL has not processed a gameweek for that squad yet, so there are no picks to read.",
  squad_not_recognised:
    "That squad has a player I do not carry, so I will not solve fourteen fifteenths of it.",
};

/**
 * Your season, not the opening squad's.
 *
 * The plan below is what the optimal opening squad does with the year, which is
 * nobody's season after the first deadline. A Team ID replaces it with the same
 * solve run on your own fifteen.
 */
function TeamEntry({
  team,
  params,
  onChange,
}: {
  team: TeamStartStatus;
  params: URLSearchParams;
  onChange: (next: URLSearchParams, options?: { replace: boolean }) => void;
}) {
  const [entered, setEntered] = useState(params.get("team") ?? "");

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
        placeholder="1234567"
        value={entered}
        onChange={(event) => setEntered(event.target.value)}
      />
      <button type="submit">Plan my season</button>
      <p className="plan-team-note" role="status">
        {team.status === "loading"
          ? "Reading your squad."
          : team.status === "ready"
            ? `Your fifteen, solved from gameweek ${String(team.event)}.`
            : team.status === "failed"
              ? TEAM_FAILURE[team.reason]
              : "Leave it blank for the optimal opening squad's season."}
      </p>
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
          className={`plan-fdr mono plan-fdr-${rating === null ? "none" : String(rating)}`}
          title={
            rating === null
              ? "No fixture, or no measured record for the opponent"
              : `Fixture difficulty ${String(rating)} of 5`
          }
        >
          {rating ?? "\u2014"}
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
        <span>FDR</span>
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
          {week.chip} · {week.transfersIn.length} free
        </p>
      ) : null}
      <ul className="plan-move">
        {week.transfersIn.map((incoming, index) => {
          const outgoing = week.transfersOut[index];
          return (
            <li key={incoming.code}>
              {outgoing ? <Shirt club={outgoing.club} /> : null}
              <span className="plan-out">{outgoing?.name ?? "\u2014"}</span>
              <ArrowRight aria-label="replaced by" size={15} />
              <Shirt club={incoming.club} />
              <span className="plan-in">{incoming.name}</span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function Why({ week, chip }: { week: PlanGameweek; chip: ChipCall | null }) {
  const fixtures = fixtureReason(week);

  return (
    <dl className="plan-why">
      <dt data-label="move">Move</dt>
      <dd>{moveReason(week)}</dd>

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

      <dt data-label="confidence">Confidence</dt>
      <dd>{confidenceReason(week)}</dd>

      <dt data-label="chip">Chip</dt>
      <dd>{chipReason(chip)}</dd>
    </dl>
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

  // What the card actually returns: the eleven, the armband again, and the
  // bench only when a boost is paying for it.
  const haul =
    week.starters.reduce(
      (total, player) => total + (week.expected[String(player.code)] ?? 0),
      0,
    ) +
    (week.expected[String(week.captain.code)] ?? 0) +
    (boosted
      ? week.bench.reduce(
          (total, player) => total + (week.expected[String(player.code)] ?? 0),
          0,
        )
      : 0);

  return (
    <li className={`plan-card plan-${week.confidence}`}>
      <div className="plan-card-head">
        <span className="plan-gw mono">GW{week.event}</span>
        <span className="plan-date mono">{deadlineDay.format(deadline)}</span>
        {chip ? <span className="plan-chip mono">{chip.chip}</span> : null}
      </div>

      <Move week={week} />
      <TeamSheet benchCounts={boosted} onOpen={onOpen} week={week} />

      <p className="plan-haul mono">
        EXPECTED HAUL {haul.toFixed(1)}
        {week.transferCostPoints > 0
          ? ` − ${week.transferCostPoints} hit = ${(haul - week.transferCostPoints).toFixed(1)}`
          : null}
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
    expected: week.expected,
    ceiling: week.expected,
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
    <details className="scatter-controls plan-chips">
      <summary className="scatter-controls-summary">
        <span>Eight chips, two of each</span>
        <span className="scatter-controls-count mono">
          {chips.filter((chip) => chip.event !== null).length} placed
        </span>
      </summary>
      <div className="scatter-controls-body">
        <p>
          Every chip comes twice a season and the first set expires at gameweek
          nineteen, so an unplayed chip is worth nothing rather than saved. Each
          is placed where it adds most, and the figure is what playing it adds
          over not playing it — not what the week scores.
        </p>
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
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}

export default function SeasonPlanPage() {
  const plan = useMemo(() => readSeasonPlan(), []);
  const [selected, setSelected] = useState<PlanPlayer | null>(null);
  const [params, setParams] = useSearchParams();
  const chips = useMemo(() => {
    const byEvent = new Map<number, ChipCall>();
    for (const chip of plan.chips) {
      if (chip.event !== null) byEvent.set(chip.event, chip);
    }
    return byEvent;
  }, [plan.chips]);

  /*
   * Nothing to solve until a manager has a squad. Between seasons FPL wipes
   * them all, so the published plan really is everyone's plan — it is what
   * Andres thinks the optimal opening squad does with the whole season. From
   * the first deadline it stops being true for anybody, and the solve below
   * takes over.
   */
  const fromEvent = Number(params.get("from") ?? "");
  const team = useTeamStart(params.get("team"));
  const live = useMemo(() => {
    // His own fifteen beats a gameweek number, because it is his season either
    // way and only one of the two knows what he owns.
    if (team.status === "ready") return team.start;
    if (!Number.isInteger(fromEvent) || fromEvent < 1 || fromEvent > 38) {
      return null;
    }
    const opening = plan.gameweeks[0];
    if (!opening) return null;

    return startFromCodes(
      [...opening.starters, ...opening.bench].map((player) => player.code),
      { bankTenths: 0, availableFreeTransfers: 1, fromEvent },
    );
  }, [fromEvent, plan.gameweeks, team]);

  const solve = useSeasonSolve(live);
  const solving = live !== null;
  const gameweeks = solving
    ? solve.gameweeks.map(asPlanGameweek)
    : plan.gameweeks;

  useDocumentTitle(
    "The season plan",
    "Every gameweek from 1 to 38: squad, eleven, captain and transfer, with " +
      "confidence that falls away the further out it reaches.",
  );

  const bands = useMemo(() => {
    const counted = new Map<Confidence, number>();
    for (const week of gameweeks) {
      counted.set(week.confidence, (counted.get(week.confidence) ?? 0) + 1);
    }
    return counted;
  }, [gameweeks]);

  return (
    <section className="season-plan" aria-label="The season plan">
      <div className="section-index" aria-hidden="true">
        02 / THE SEASON
      </div>

      <RouteHeading>Every gameweek to the end.</RouteHeading>

      <TeamEntry team={team} params={params} onChange={setParams} />

      <details className="scatter-controls plan-preamble">
        <summary className="scatter-controls-summary">
          <span>What this is, and how to read it</span>
          <span className="scatter-controls-count mono">
            GW{gameweeks[0]?.event}–{gameweeks[gameweeks.length - 1]?.event}
            {solving ? null : ` · ${plan.netExpectedPoints.toFixed(0)} NET`}
          </span>
        </summary>
        <div className="scatter-controls-body">
          <p className="lede">
            Gameweek {gameweeks[0]?.event} to{" "}
            {gameweeks[gameweeks.length - 1]?.event}: the squad, the eleven, the
            captain and the transfer, for all of it.{" "}
            {solving ? null : (
              <>
                <strong>{plan.netExpectedPoints.toFixed(0)}</strong> net points
                from the opening squad.
              </>
            )}
          </p>

          {solving ? (
            <p className="plan-honesty">
              Solved on your machine, not on a server: the plan depends on your
              squad, your bank and your free transfers, so it cannot be
              precomputed, and thirty-eight gameweeks does not fit in a
              fifteen-second function. Nothing about your team is sent anywhere
              to produce it.
            </p>
          ) : (
            <p className="plan-honesty">
              Between seasons FPL wipes every squad, so this one plan really is
              everyone&rsquo;s — it is what the opening fifteen does with the
              whole season. {bands.get("firm") ?? 0} gameweek is firm,{" "}
              {bands.get("projected") ?? 0} are projected,{" "}
              {bands.get("provisional") ?? 0} are provisional. A single optimal
              38-gameweek solve does not return, so this is {plan.windowsSolved}{" "}
              overlapping windows chained together from a pool of{" "}
              {plan.poolSize} players — a good plan, not a proof.
            </p>
          )}

          <dl className="plan-key">
            <div>
              <dt>xPts</dt>
              <dd>
                Expected FPL points from one match: appearance, goals and
                assists at his own decayed per-90 rates, plus clean sheets,
                saves, cards and defensive contribution, scaled by this
                opponent. A good starter is four to six; anything above seven is
                a genuinely strong fixture.
              </dd>
            </div>
            <div>
              <dt>xCeil</dt>
              <dd>
                The same match on his best afternoon: xPts multiplied by how far
                his ninetieth-percentile score sat above his average last
                season. A centre-half who plays ninety and does nothing lands
                near twice his xPts; a striker who either scores or vanishes
                nearer three times it. An armband and a chip are played for this
                number, not the first one.
              </dd>
            </div>
            <div>
              <dt>FDR</dt>
              <dd>
                One to five, from the measured strength of both sides at the
                venue the match is played. One is the softest tie, five the
                hardest, and a dash means a blank or an opponent with no record.
              </dd>
            </div>
            <div>
              <dt>Opponent</dt>
              <dd>
                Capitals are home, lower case away.{" "}
                <span className="mono">HUL</span> is at home to Hull;{" "}
                <span className="mono">hul</span> is away at Hull.
              </dd>
            </div>
            <div>
              <dt>Captain</dt>
              <dd>
                Shown <strong>doubled</strong>, because that is what he returns.
                Bench figures are bracketed unless a Bench Boost is paying for
                them.
              </dd>
            </div>
          </dl>
        </div>
      </details>

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
          The solver stopped: {solve.reason}. The published opening-squad plan
          is still below.
        </p>
      ) : null}

      <ChipStrategy chips={plan.chips} />

      <ul className="plan-rail">
        {gameweeks.map((week) => (
          <GameweekCard
            chip={chips.get(week.event) ?? null}
            key={week.event}
            onOpen={setSelected}
            week={week}
          />
        ))}
      </ul>

      {selected ? (
        <PlayerDetail
          onClose={() => {
            setSelected(null);
          }}
          player={selected}
        />
      ) : null}

      <p className="plan-basis mono">
        {plan.basis}. Records from {plan.recordSeason}. Transfer rules:{" "}
        {plan.rulesReference}.
      </p>

      <section className="plan-caveats" aria-label="What this plan cannot know">
        <h2>Three things to hold against it</h2>
        <ol>
          <li>
            <strong>The promoted clubs have no record.</strong> Every projection
            here comes from {plan.recordSeason}, a season{" "}
            {plan.dataGaps.clubsWithoutRecord.length > 0 ? (
              <>
                {plan.dataGaps.clubsWithoutRecord.join(" and ")} did not play in
              </>
            ) : (
              <>the promoted clubs did not play in</>
            )}
            . Their players are missing from the pool entirely, and fixtures
            against them are rated as exactly average because there is no
            measured strength to rate them by. {plan.dataGaps.clubsInPool} of{" "}
            {plan.dataGaps.clubsInLeague} clubs are represented.
          </li>
          <li>
            <strong>It cannot see price changes.</strong> Players rise and fall
            through the season and this plan holds today&rsquo;s prices for all
            thirty-eight gameweeks. A transfer eleven weeks out may simply be
            unaffordable by the time you reach it, and a squad that banks value
            early can afford things this plan says it cannot.
          </li>
          <li>
            <strong>It does not yet adjust week to week.</strong> A real plan
            moves with form, minutes, injuries and price changes, and against
            what your mini-league already owns. None of that is in here: this is
            last season&rsquo;s scoring record scaled by this season&rsquo;s
            fixtures, and nothing else.
          </li>
          <li>
            <strong>It will change every gameweek.</strong> That is not a
            failure of the plan, it is what a plan is for. Read the shape — the
            weeks worth a chip, the runs worth holding through — and expect the
            names past the next month or so to be replaced.
          </li>
          <li>
            <strong>No Haaland, and that is the model talking.</strong> He is
            projected at 4.40 points a match against Thiago&rsquo;s 4.41 for
            half the price, because his decayed start rate is 0.68 against
            Thiago&rsquo;s 0.90. Spend the difference on the eleven and the
            eleven wins. If you think 0.68 understates him, that is the number
            to argue with, not the optimiser.
          </li>
        </ol>
      </section>
    </section>
  );
}
