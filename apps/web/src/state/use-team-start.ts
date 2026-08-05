import { useEffect, useState } from "react";

import type { SolveStart } from "./season-solver";
import { startFromElementIds } from "./season-solver";
import {
  readDeclaredSquad,
  SQUAD_BUDGET_TENTHS,
  validateDeclaredSquad,
} from "./declared-squad";
import {
  readDeclaredTransfers,
  squadAfterDeclared,
  type DeclaredTransfer,
} from "./declared-transfers";
import { refreshTeamAnalysis } from "./team-analysis";

/**
 * The gameweek a pre-season squad is declared for. FPL has processed nothing
 * before it, so there is no published squad to correct — only the manager's
 * own fifteen, locked in as though it had been played.
 */
export const PRE_SEASON_EVENT = 1;

/**
 * A manager's own squad, turned into somewhere for the solver to start.
 *
 * The plan page is otherwise the optimal opening squad's season, which stops
 * being anybody's season the moment the first deadline passes. Given a team ID
 * it becomes that manager's season instead: same solver, his fifteen.
 *
 * FPL publishes a manager's picks only for gameweeks that have been processed,
 * so the squad read here is the one he finished the last gameweek with. Any
 * transfer made since is invisible until the next deadline passes — see
 * `declared_transfers` for how a manager tells us about it.
 */

export type TeamStartStatus =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "ready";
      start: SolveStart;
      event: number;
      declared: readonly DeclaredTransfer[];
      /**
       * Whether the fifteen came from FPL's published picks or from the
       * manager's own pre-season declaration. Never blurred: one is observed,
       * the other is his claim.
       */
      source: "published" | "declared";
    }
  | { status: "failed"; reason: TeamStartFailure };

export type TeamStartFailure =
  | "not_a_team_id"
  | "unreachable"
  | "no_processed_event"
  | "squad_not_recognised";

export function useTeamStart(
  raw: string | null,
  /** Bumped by the caller when a transfer is declared, to read the squad again. */
  declaredAt = 0,
): TeamStartStatus {
  // Derived, not stored: a blank box and a nonsense box are both answerable
  // without asking FPL anything, and putting them in state would mean a render
  // pass to say so.
  const entryId = raw === null ? null : Number(raw);
  const usable =
    entryId !== null &&
    Number.isInteger(entryId) &&
    entryId >= 1 &&
    entryId <= 4_294_967_295;

  const [fetched, setFetched] = useState<TeamStartStatus | null>(null);

  useEffect(() => {
    if (!usable || entryId === null) return;

    const controller = new AbortController();
    let settled = false;
    refreshTeamAnalysis(entryId, null, {
      storage: window.localStorage,
      signal: controller.signal,
    })
      .then((result) => {
        if (controller.signal.aborted) return;
        settled = true;
        if (result.status !== "ready" && result.status !== "stale") {
          const preSeason =
            result.status === "unavailable" &&
            result.reason === "no_processed_event"
              ? startFromDeclaredSquad(entryId)
              : null;
          if (preSeason) {
            setFetched(preSeason);
            return;
          }
          setFetched({
            status: "failed",
            reason:
              result.status === "unavailable" &&
              result.reason === "no_processed_event"
                ? "no_processed_event"
                : "unreachable",
          });
          return;
        }
        const team = result.state;
        // His picks are the gameweek just gone, so the plan starts at the next.
        const fromEvent = team.event + 1;
        // Anything he has told us about that FPL has not published yet. Read
        // from his own browser, so it can only ever be his claim about his own
        // squad — a Team ID is public, and a server copy could be forged.
        const declared = readDeclaredTransfers(
          window.localStorage,
          entryId,
          fromEvent,
        );
        const start = startFromElementIds(
          squadAfterDeclared(
            team.picks.map((pick) => pick.elementId),
            declared,
          ),
          {
            bankTenths: team.bankTenths,
            availableFreeTransfers: 1,
            fromEvent,
          },
        );
        setFetched(
          start
            ? {
                status: "ready",
                start,
                event: fromEvent,
                declared,
                source: "published",
              }
            : { status: "failed", reason: "squad_not_recognised" },
        );
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        settled = true;
        setFetched({ status: "failed", reason: "unreachable" });
      });

    return () => {
      controller.abort();
      // A new team id must not show the previous one's answer.
      if (!settled) setFetched(null);
    };
  }, [entryId, usable, declaredAt]);

  if (raw === null) return { status: "idle" };
  if (!usable) return { status: "failed", reason: "not_a_team_id" };
  return fetched ?? { status: "loading" };
}

/**
 * The manager's own fifteen, treated as if it had been played in gameweek one.
 *
 * Nothing is invented: a squad only becomes a start when it obeys every
 * published rule, and the bank is what the hundred million minus his own
 * prices leaves. Absent or broken, the caller falls back to saying so.
 */
function startFromDeclaredSquad(entryId: number): TeamStartStatus | null {
  const stored = readDeclaredSquad(
    window.localStorage,
    entryId,
    PRE_SEASON_EVENT,
  );
  if (!stored) return null;
  const validation = validateDeclaredSquad(stored.elementIds);
  if (!validation.valid) return null;

  const start = startFromElementIds(stored.elementIds, {
    bankTenths: SQUAD_BUDGET_TENTHS - validation.summary.spentTenths,
    // Gameweek one is squad selection, not a transfer window, and the solver
    // zeroes the allowance for the opener regardless.
    availableFreeTransfers: 0,
    fromEvent: PRE_SEASON_EVENT,
  });
  return start
    ? {
        status: "ready",
        start,
        event: PRE_SEASON_EVENT,
        declared: [],
        source: "declared",
      }
    : null;
}
