import { useEffect, useMemo, useState } from "react";

import type { SolveAssumption, SolveStart } from "./season-solver";
import {
  PLAYERS_BY_ELEMENT_ID,
  SEASON_DEADLINES,
  SEASON_EVENTS,
  startFromElementIds,
} from "./season-solver";
import {
  readDeclaredSquad,
  saveDeclaredSquad,
  SQUAD_BUDGET_TENTHS,
  validateDeclaredSquad,
} from "./declared-squad";
import { decodeSquad } from "./squad-code";
import {
  readDeclaredTransfers,
  squadAfterDeclared,
  type DeclaredTransfer,
} from "./declared-transfers";
import { refreshTeamAnalysis } from "./team-analysis";
import { loadTeamStateOverrides } from "./team-state-overrides";
import {
  initialTeamAnalysisState,
  loadCachedPublicTeamState,
  type TeamAnalysisState,
} from "./team-analysis";

/**
 * The gameweek a pre-season squad is declared for. FPL has processed nothing
 * before it, so there is no published squad to correct — only the manager's
 * own fifteen, locked in as though it had been played.
 */
export const PRE_SEASON_EVENT = 1;

/**
 * Assumed when the manager has not said otherwise. One is the commonest state
 * and the least dangerous guess: assuming more would plan moves he cannot make.
 */
const DEFAULT_FREE_TRANSFERS = 1;

export function currentPlanningEvent(now: Date = new Date()): number {
  const index = SEASON_DEADLINES.findIndex(
    (deadline) => new Date(deadline).getTime() > now.getTime(),
  );
  return SEASON_EVENTS[index < 0 ? SEASON_EVENTS.length - 1 : index] ?? 1;
}

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
  | "squad_not_projectable"
  | "squad_not_recognised";

/**
 * The squad, and the raw analysis it was derived from.
 *
 * Both are wanted on the same page: the start feeds the solver, the analysis
 * feeds the snapshot the reader looks at. Deriving one and discarding the other
 * meant the page had to ask FPL twice for the same thing, and that endpoint is
 * rate limited.
 */
export interface TeamPlan {
  start: TeamStartStatus;
  analysis: TeamAnalysisState;
  retry: () => void;
}

export function useTeamPlan(
  raw: string | null,
  /** Bumped by the caller when a transfer is declared, to read the squad again. */
  declaredAt = 0,
  /**
   * A declared fifteen carried in the link, used only when this browser has
   * none. Read here rather than restored by the page because the squad is read
   * after FPL answers, and a restore racing that would arrive too late.
   */
  squadCode: string | null = null,
): TeamPlan {
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
  const [resolved, setResolved] = useState<TeamAnalysisState | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Read outside the effect: a cached snapshot is shown while the refresh runs,
  // and setting that from inside the effect is a cascading render. Keyed on the
  // team alone — once a refresh lands its result supersedes this.
  const cached = useMemo(
    () =>
      usable && entryId !== null
        ? loadCachedPublicTeamState(window.localStorage, entryId)
        : null,
    [entryId, usable],
  );

  useEffect(() => {
    if (!usable || entryId === null) return;

    const controller = new AbortController();
    let settled = false;
    refreshTeamAnalysis(entryId, cached, {
      storage: window.localStorage,
      signal: controller.signal,
    })
      .then((result) => {
        if (controller.signal.aborted) return;
        settled = true;
        setResolved(result);
        if (result.status !== "ready" && result.status !== "stale") {
          const declaredStart = startFromDeclaredSquad(
            entryId,
            currentPlanningEvent(),
            squadCode,
          );
          if (declaredStart) {
            setFetched(declaredStart);
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
        // What FPL cannot publish and only the manager knows: how many free
        // transfers he is holding, what he paid for his squad, and how much is
        // really in the bank after a move FPL has not processed. The form that
        // collects these was writing to storage nobody read.
        const corrections = loadTeamStateOverrides(
          window.localStorage,
          entryId,
          team.stateAsOf,
        );
        const sellingPrices = new Map(
          (corrections?.currentSquad ?? []).map((player) => [
            player.elementId,
            player.sellingPriceTenths,
          ]),
        );
        const assumed: SolveAssumption[] =
          corrections?.availableFreeTransfers === null ||
          corrections?.availableFreeTransfers === undefined
            ? ["free_transfers"]
            : [];
        const start = startFromElementIds(
          squadAfterDeclared(
            team.picks.map((pick) => pick.elementId),
            declared,
          ),
          {
            bankTenths: corrections?.bankTenths ?? team.bankTenths,
            availableFreeTransfers:
              corrections?.availableFreeTransfers ?? DEFAULT_FREE_TRANSFERS,
            fromEvent,
            sellingPrices,
            assumed,
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
        // The snapshot has to hear about this too, or the page sits on
        // "loading" forever while the solver has already given up.
        setResolved({ status: "error", reason: "network_error" });
        setFetched({ status: "failed", reason: "unreachable" });
      });

    return () => {
      controller.abort();
      // A new team id must not show the previous one's answer.
      if (!settled) {
        setFetched(null);
        setResolved(null);
      }
    };
  }, [entryId, usable, declaredAt, attempt, cached, squadCode]);

  const start: TeamStartStatus =
    raw === null
      ? { status: "idle" }
      : !usable
        ? { status: "failed", reason: "not_a_team_id" }
        : (fetched ?? { status: "loading" });

  const analysis: TeamAnalysisState =
    raw === null || !usable
      ? initialTeamAnalysisState
      : (resolved ??
        (cached
          ? { status: "refreshing", state: cached }
          : { status: "loading" }));

  return {
    start,
    analysis,
    retry: () => {
      // Clearing first is what makes the click visible. Without it the previous
      // failure stayed on screen for the whole request, so a retry that failed
      // the same way changed nothing a reader could see.
      setResolved(null);
      setFetched(null);
      setAttempt((previous) => previous + 1);
    },
  };
}

/** The squad alone, for callers with no use for the snapshot behind it. */
export function useTeamStart(
  raw: string | null,
  declaredAt = 0,
): TeamStartStatus {
  return useTeamPlan(raw, declaredAt).start;
}

/**
 * The manager's own fifteen, treated as if it had been played in gameweek one.
 *
 * Nothing is invented: a squad only becomes a start when it obeys every
 * published rule, and the bank is what the hundred million minus his own
 * prices leaves. Absent or broken, the caller falls back to saying so.
 */
function startFromDeclaredSquad(
  entryId: number,
  event: number = PRE_SEASON_EVENT,
  squadCode: string | null = null,
): TeamStartStatus | null {
  const stored = readDeclaredSquad(window.localStorage, entryId, event);
  const elementIds = stored?.elementIds ?? fromLink(entryId, event, squadCode);
  if (!elementIds) return null;

  // The declaration is made against the whole FPL list; the solver only holds
  // the players it can project. A squad it cannot price must say so rather than
  // fall through to the generic plan, which reads as "your squad was ignored".
  const unprojectable = elementIds.filter(
    (id) => !PLAYERS_BY_ELEMENT_ID.has(id),
  );
  if (unprojectable.length > 0) {
    return { status: "failed", reason: "squad_not_projectable" };
  }

  const opening = event === PRE_SEASON_EVENT;
  const validation = validateDeclaredSquad(elementIds, PLAYERS_BY_ELEMENT_ID, {
    enforceOpeningBudget: opening,
  });
  if (!validation.valid) return null;

  const start = startFromElementIds(elementIds, {
    bankTenths: opening
      ? SQUAD_BUDGET_TENTHS - validation.summary.spentTenths
      : 0,
    // Gameweek one is squad selection, not a transfer window, and the solver
    // zeroes the allowance for the opener regardless.
    availableFreeTransfers: opening ? 0 : DEFAULT_FREE_TRANSFERS,
    fromEvent: event,
    // He is buying at today's price this minute, so the list price IS his
    // purchase price. Nothing is assumed here, unlike a published squad whose
    // purchase prices FPL keeps private.
    ...(opening
      ? {
          sellingPrices: new Map(
            elementIds.map((elementId) => [
              elementId,
              PLAYERS_BY_ELEMENT_ID.get(elementId)?.priceTenths ?? 0,
            ]),
          ),
        }
      : { assumed: ["bank", "free_transfers"] as SolveAssumption[] }),
  });
  return start
    ? {
        status: "ready",
        start,
        event,
        declared: [],
        source: "declared",
      }
    : null;
}

/**
 * The fifteen a link is carrying, kept in this browser on the way past.
 *
 * Used only when nothing is stored, so a link can never overwrite the squad a
 * manager is looking at. Persisting is best effort: private browsing refuses
 * the write, and the link should still plan his season.
 */
function fromLink(
  entryId: number,
  event: number,
  squadCode: string | null,
): number[] | null {
  if (squadCode === null) return null;
  const elementIds = decodeSquad(squadCode);
  if (!elementIds) return null;
  try {
    saveDeclaredSquad(
      window.localStorage,
      entryId,
      event,
      elementIds,
      PLAYERS_BY_ELEMENT_ID,
      () => new Date(),
      { enforceOpeningBudget: event === PRE_SEASON_EVENT },
    );
  } catch {
    // Storage full or blocked. The squad still plans; it just will not persist.
  }
  return elementIds;
}
