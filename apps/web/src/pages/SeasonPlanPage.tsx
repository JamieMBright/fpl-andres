import { ArrowRight, ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { CeefaxShirt } from "../components/CeefaxShirt";
import { RouteHeading } from "../components/RouteHeading";
import { deadlineDay, money } from "../format";
import { kitForShortName } from "../kit/team-kits";
import type { SolvedGameweek } from "../state/season-solver";
import { startFromCodes } from "../state/season-solver";
import { useSeasonSolve } from "../state/use-season-solve";
import type {
  ChipCall,
  Confidence,
  PlanGameweek,
  PlanPlayer,
} from "../state/season-plan";
import { CONFIDENCE_NOTE, readSeasonPlan } from "../state/season-plan";
import { useDocumentTitle } from "../state/use-document-title";

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

function TeamSheet({ week }: { week: PlanGameweek }) {
  const role = (player: PlanPlayer) => {
    if (player.code === week.captain.code) return "C";
    if (player.code === week.viceCaptain.code) return "V";
    return null;
  };

  const line = (player: PlanPlayer, benched: boolean) => {
    const badge = role(player);
    const against = week.opponents[player.club] ?? [];
    const points = week.expected[String(player.code)] ?? 0;

    return (
      <li key={player.code}>
        <Shirt club={player.club} />
        <span className="plan-name">{player.name}</span>
        {badge ? (
          <span className={`plan-role plan-role-${badge.toLowerCase()}`}>
            {badge}
          </span>
        ) : (
          <span className="plan-role-gap" aria-hidden="true" />
        )}
        <span className="plan-price mono">
          {money.format(player.priceTenths / 10)}
        </span>
        <span className="plan-against mono">
          {against.length === 0 ? "blank" : against.join(" ")}
        </span>
        <span className="plan-points mono">
          {benched ? `(${points.toFixed(1)})` : points.toFixed(1)}
        </span>
      </li>
    );
  };

  return (
    <div className="plan-sheet">
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
        {week.event === 1 ? (
          <>
            <span className="mono">Opening squad</span> — no transfer exists to
            spend before the first deadline. Captain{" "}
            <strong>{week.captain.name}</strong>.
          </>
        ) : (
          <>
            <span className="mono">Roll</span> — bank the transfer, captain{" "}
            <strong>{week.captain.name}</strong>.
          </>
        )}
      </p>
    );
  }

  return (
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
  );
}

function Why({ week, chip }: { week: PlanGameweek; chip: ChipCall | null }) {
  const cost =
    week.transferCostPoints > 0
      ? `Takes a ${week.transferCostPoints}-point hit.`
      : "No hit: inside the free transfer.";
  const benched =
    week.bench.reduce((total, player) => total + player.priceTenths, 0) / 10;

  return (
    <div className="plan-why">
      <p>
        {week.transfersIn.length === 0
          ? week.event === 1
            ? "The opening squad, picked before a ball is kicked."
            : "Nothing available gains more than holding, so the transfer banks for a week when it does."
          : cost}{" "}
        Projected <strong>{week.projectedPoints.toFixed(1)}</strong> before
        cost, <strong>{week.netExpectedPoints.toFixed(1)}</strong> after.
      </p>
      <p>
        {CONFIDENCE_NOTE[week.confidence]} Bank after this move{" "}
        {money.format(week.bankAfterTenths / 10)}.
      </p>
      <p className="plan-bench-note">
        {money.format(benched)} is on the bench, which scores nothing unless a
        starter does not play. Bench order is by expected points, not by
        FPL&rsquo;s substitution rules — those depend on the formation left
        behind, which is not solved here.
      </p>
      {chip ? (
        <p className="plan-chip-note">
          <strong>{chip.chip}:</strong> {chip.note}.
        </p>
      ) : null}
    </div>
  );
}

function GameweekCard({
  week,
  chip,
  open,
  onToggle,
}: {
  week: PlanGameweek;
  chip: ChipCall | null;
  open: boolean;
  onToggle: () => void;
}) {
  const deadline = new Date(week.deadline);
  const value =
    [...week.starters, ...week.bench].reduce(
      (total, player) => total + player.priceTenths,
      0,
    ) / 10;

  return (
    <li className={`plan-card plan-${week.confidence}`}>
      <div className="plan-card-head">
        <span className="plan-gw mono">GW{week.event}</span>
        <span className="plan-date mono">{deadlineDay.format(deadline)}</span>
        {chip ? <span className="plan-chip mono">{chip.chip}</span> : null}
      </div>

      <Move week={week} />
      <TeamSheet week={week} />

      <p className="plan-value mono">
        Squad {money.format(value)} · bank{" "}
        {money.format(week.bankAfterTenths / 10)}
      </p>

      <button
        aria-expanded={open}
        className="plan-toggle"
        onClick={onToggle}
        type="button"
      >
        Why <ChevronDown aria-hidden="true" size={14} />
      </button>
      {open ? <Why week={week} chip={chip} /> : null}
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
    expected: week.expected,
    freeTransfersBefore: week.freeTransfersBefore,
    paidTransfers: week.paidTransfers,
    transferCostPoints: week.transferCostPoints,
    projectedPoints: week.projectedPoints,
    netExpectedPoints: week.netExpectedPoints,
    bankAfterTenths: week.bankAfterTenths,
  };
}

export default function SeasonPlanPage() {
  const plan = useMemo(() => readSeasonPlan(), []);
  const [params] = useSearchParams();
  const [open, setOpen] = useState<number | null>(
    plan.gameweeks[0]?.event ?? null,
  );
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
  const live = useMemo(() => {
    if (!Number.isInteger(fromEvent) || fromEvent < 1 || fromEvent > 38) {
      return null;
    }
    const opening = plan.gameweeks[0];
    if (!opening) return null;

    return startFromCodes(
      [...opening.starters, ...opening.bench].map((player) => player.code),
      { bankTenths: 0, availableFreeTransfers: 1, fromEvent },
    );
  }, [fromEvent, plan.gameweeks]);

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

      <p className="lede">
        Gameweek {gameweeks[0]?.event} to{" "}
        {gameweeks[gameweeks.length - 1]?.event}: the squad, the eleven, the
        captain and the transfer, for all of it.{" "}
        {solving ? null : (
          <>
            <strong>{plan.netExpectedPoints.toFixed(0)}</strong> net points from
            the opening squad.
          </>
        )}
      </p>

      {solving ? (
        <p className="plan-honesty">
          Solved on your machine, not on a server: the plan depends on your
          squad, your bank and your free transfers, so it cannot be precomputed,
          and thirty-eight gameweeks does not fit in a fifteen-second function.
          Nothing about your team is sent anywhere to produce it.
        </p>
      ) : (
        <p className="plan-honesty">
          Between seasons FPL wipes every squad, so this one plan really is
          everyone&rsquo;s — it is what the opening fifteen does with the whole
          season. {bands.get("firm") ?? 0} gameweek is firm,{" "}
          {bands.get("projected") ?? 0} are projected,{" "}
          {bands.get("provisional") ?? 0} are provisional. A single optimal
          38-gameweek solve does not return, so this is {plan.windowsSolved}{" "}
          overlapping windows chained together from a pool of {plan.poolSize}{" "}
          players — a good plan, not a proof.
        </p>
      )}

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

      <ul className="plan-rail">
        {gameweeks.map((week) => (
          <GameweekCard
            chip={chips.get(week.event) ?? null}
            key={week.event}
            onToggle={() => setOpen(open === week.event ? null : week.event)}
            open={open === week.event}
            week={week}
          />
        ))}
      </ul>

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
        </ol>
      </section>
    </section>
  );
}
