import { ArrowRight, ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { CeefaxShirt } from "../components/CeefaxShirt";
import { RouteHeading } from "../components/RouteHeading";
import { deadlineDay, money } from "../format";
import { kitForShortName } from "../kit/team-kits";
import {
  CONFIDENCE_NOTE,
  readSeasonPlan,
  type Confidence,
  type PlanGameweek,
  type PlanPlayer,
} from "../state/season-plan";
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

  return (
    <div className="plan-sheet">
      <ol className="plan-eleven">
        {week.starters.map((player) => (
          <li key={player.code}>
            <Shirt club={player.club} />
            <span className="plan-name">{player.name}</span>
            <span className="plan-club mono">{player.club}</span>
            {role(player) ? (
              <span
                className={`plan-role plan-role-${role(player)?.toLowerCase()}`}
              >
                {role(player)}
              </span>
            ) : null}
          </li>
        ))}
      </ol>
      <ol className="plan-bench" aria-label="Bench in order">
        {week.bench.map((player) => (
          <li key={player.code}>
            <Shirt club={player.club} />
            <span className="plan-name">{player.name}</span>
            <span className="plan-club mono">{player.club}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Move({ week }: { week: PlanGameweek }) {
  if (week.transfersIn.length === 0) {
    return (
      <p className="plan-move plan-move-roll">
        <span className="mono">Roll</span> — bank the transfer, captain{" "}
        <strong>{week.captain.name}</strong>.
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

function Why({ week, chip }: { week: PlanGameweek; chip: boolean }) {
  const cost =
    week.transferCostPoints > 0
      ? `Takes a ${week.transferCostPoints}-point hit.`
      : "No hit: inside the free transfer.";

  return (
    <div className="plan-why">
      <p>
        {week.transfersIn.length === 0
          ? "Nothing available gains more than holding, so the transfer banks for a week when it does."
          : cost}{" "}
        Projected <strong>{week.projectedPoints.toFixed(1)}</strong> before
        cost, <strong>{week.netExpectedPoints.toFixed(1)}</strong> after.
      </p>
      <p>
        {CONFIDENCE_NOTE[week.confidence]} Bank after this move{" "}
        {money.format(week.bankAfterTenths / 10)}.
      </p>
      <p className="plan-bench-note">
        Bench is ordered by expected points, not by FPL&rsquo;s substitution
        rules — those depend on the formation left behind when someone does not
        play, which is not solved here.
      </p>
      {chip ? (
        <p className="plan-chip-note">
          One of the two easiest fixture runs of the season. A chip window on
          fixture difficulty alone — chip timing is not solved, because the
          multiplier and bench behaviour it needs is not published.
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
  chip: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const deadline = new Date(week.deadline);

  return (
    <li className={`plan-card plan-${week.confidence}`}>
      <div className="plan-card-head">
        <span className="plan-gw mono">GW{week.event}</span>
        <span className="plan-date mono">{deadlineDay.format(deadline)}</span>
        {chip ? <span className="plan-chip mono">CHIP</span> : null}
      </div>

      <Move week={week} />
      <TeamSheet week={week} />

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

export default function SeasonPlanPage() {
  const plan = useMemo(() => readSeasonPlan(), []);
  const [open, setOpen] = useState<number | null>(
    plan.gameweeks[0]?.event ?? null,
  );
  const chips = useMemo(() => new Set(plan.chipWindows), [plan.chipWindows]);

  useDocumentTitle(
    "The season plan",
    "Every gameweek from 1 to 38: squad, eleven, captain and transfer, with " +
      "confidence that falls away the further out it reaches.",
  );

  const bands = useMemo(() => {
    const counted = new Map<Confidence, number>();
    for (const week of plan.gameweeks) {
      counted.set(week.confidence, (counted.get(week.confidence) ?? 0) + 1);
    }
    return counted;
  }, [plan.gameweeks]);

  return (
    <section className="season-plan" aria-label="The season plan">
      <div className="section-index" aria-hidden="true">
        02 / THE SEASON
      </div>

      <RouteHeading>Every gameweek to the end.</RouteHeading>

      <p className="lede">
        Gameweek {plan.gameweeks[0]?.event} to{" "}
        {plan.gameweeks[plan.gameweeks.length - 1]?.event}: the squad, the
        eleven, the captain and the transfer, for all of it.{" "}
        <strong>{plan.netExpectedPoints.toFixed(0)}</strong> net points from the
        opening squad.
      </p>

      <p className="plan-honesty">
        It gets less reliable the further out you read, and it says so on every
        card. {bands.get("firm") ?? 0} gameweek is firm,{" "}
        {bands.get("projected") ?? 0} are projected,{" "}
        {bands.get("provisional") ?? 0} are provisional. A single optimal
        38-gameweek solve does not return, so this is {plan.windowsSolved}{" "}
        overlapping windows chained together from a pool of {plan.poolSize}{" "}
        players — a good plan, not a proof.
      </p>

      <ul className="plan-rail">
        {plan.gameweeks.map((week) => (
          <GameweekCard
            chip={chips.has(week.event)}
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
    </section>
  );
}
