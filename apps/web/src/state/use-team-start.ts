import { useEffect, useMemo, useRef, useState } from "react";
import type { PublicTeamState } from "@fpl-andres/contracts";

import type { SolveAssumption, SolveStart } from "./season-solver";
import { PLAYERS_BY_ELEMENT_ID, startFromElementIds } from "./season-solver";
import { deadlineAfterEvent, planningEventAt } from "./season-deadlines";
import {
  declaredSquadPlanningValues,
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
  usableUntilNextDeadline,
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
const FOREGROUND_REFRESH_MS = 15 * 60 * 1_000;

export function currentPlanningEvent(now: Date = new Date()): number {
  return planningEventAt(now);
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

  const [resolved, setResolved] = useState<{
    entryId: number;
    attempt: number;
    result: TeamAnalysisState;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const lastRequestedAt = useRef(0);

  // Read outside the effect: a cached snapshot is shown while the refresh runs,
  // and setting that from inside the effect is a cascading render. Keyed on the
  // team alone — once a refresh lands its result supersedes this.
  const cached = useMemo(() => {
    void attempt;
    if (!usable || entryId === null) return null;
    try {
      return loadCachedPublicTeamState(window.localStorage, entryId);
    } catch {
      return null;
    }
  }, [entryId, usable, attempt]);

  const prior = resolved?.entryId === entryId ? resolved.result : null;
  const previous =
    prior &&
    (prior.status === "ready" || prior.status === "stale") &&
    usableUntilNextDeadline(prior.state.event, new Date())
      ? prior.state
      : cached && usableUntilNextDeadline(cached.event, new Date())
        ? cached
        : null;
  const previousRef = useRef(previous);
  useEffect(() => {
    previousRef.current = previous;
  }, [previous]);

  useEffect(() => {
    if (!usable || entryId === null) return;

    const controller = new AbortController();
    lastRequestedAt.current = Date.now();
    refreshTeamAnalysis(entryId, previousRef.current, {
      storage: browserStorage(),
      signal: controller.signal,
    })
      .then((result) => {
        if (controller.signal.aborted) return;
        setResolved({ entryId, attempt, result });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        const saved = previousRef.current;
        setResolved({
          entryId,
          attempt,
          result:
            saved && usableUntilNextDeadline(saved.event, new Date())
              ? { status: "stale", state: saved, reason: "network_error" }
              : { status: "error", reason: "network_error" },
        });
      });

    return () => {
      controller.abort();
    };
  }, [entryId, usable, declaredAt, attempt, cached, squadCode]);

  const snapshotEvent = previous?.event;
  useEffect(() => {
    if (snapshotEvent === undefined) return;
    const deadline = deadlineAfterEvent(snapshotEvent);
    if (!deadline) return;
    const timer = window.setTimeout(
      () => setAttempt((value) => value + 1),
      Math.min(
        2_147_483_647,
        Math.max(0, Date.parse(deadline.deadline) - Date.now()),
      ),
    );
    return () => window.clearTimeout(timer);
  }, [snapshotEvent, attempt]);

  useEffect(() => {
    if (!usable) return;
    const refresh = () => setAttempt((previous) => previous + 1);
    const onVisible = () => {
      if (
        document.visibilityState === "visible" &&
        Date.now() - lastRequestedAt.current >= FOREGROUND_REFRESH_MS
      ) {
        refresh();
      }
    };
    window.addEventListener("online", refresh);
    window.addEventListener("storage", refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("online", refresh);
      window.removeEventListener("storage", refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [usable]);

  const analysis = useMemo<TeamAnalysisState>(
    () =>
      raw === null || !usable
        ? initialTeamAnalysisState
        : resolved?.entryId === entryId && resolved.attempt === attempt
          ? resolved.result
          : previous
            ? { status: "refreshing", state: previous }
            : { status: "loading" },
    [raw, usable, resolved, entryId, attempt, previous],
  );

  const start = useMemo<TeamStartStatus>(() => {
    void declaredAt;
    if (raw === null) return { status: "idle" };
    if (!usable || entryId === null)
      return { status: "failed", reason: "not_a_team_id" };
    if (
      analysis.status === "ready" ||
      analysis.status === "stale" ||
      analysis.status === "refreshing"
    ) {
      return startFromPublicState(analysis.state);
    }
    const declared = startFromDeclaredSquad(
      entryId,
      currentPlanningEvent(),
      squadCode,
    );
    if (declared) return declared;
    if (analysis.status === "loading") return { status: "loading" };
    return {
      status: "failed",
      reason:
        analysis.status === "unavailable" &&
        analysis.reason === "no_processed_event"
          ? "no_processed_event"
          : "unreachable",
    };
  }, [raw, usable, entryId, analysis, declaredAt, squadCode]);

  return {
    start,
    analysis,
    retry: () => {
      // Clearing first is what makes the click visible. Without it the previous
      // failure stayed on screen for the whole request, so a retry that failed
      // the same way changed nothing a reader could see.
      setAttempt((previous) => previous + 1);
    },
  };
}

function startFromPublicState(team: PublicTeamState): TeamStartStatus {
  const fromEvent = team.event + 1;
  let declared: readonly DeclaredTransfer[] = [];
  let corrections: ReturnType<typeof loadTeamStateOverrides> = null;
  try {
    declared = readDeclaredTransfers(
      window.localStorage,
      team.entryId,
      fromEvent,
    );
    corrections = loadTeamStateOverrides(
      window.localStorage,
      team.entryId,
      team.stateAsOf,
    );
  } catch {
    declared = [];
    corrections = null;
  }
  const publicSellingPrices = new Map(
    team.picks.flatMap((pick) =>
      pick.sellingPriceTenths === null
        ? []
        : [[pick.elementId, pick.sellingPriceTenths] as const],
    ),
  );
  const sellingPrices = corrections?.currentSquad
    ? new Map(
        corrections.currentSquad.map((player) => [
          player.elementId,
          player.sellingPriceTenths,
        ]),
      )
    : publicSellingPrices;
  const assumed: SolveAssumption[] =
    corrections?.availableFreeTransfers == null ? ["free_transfers"] : [];
  const start = startFromElementIds(
    squadAfterDeclared(
      team.picks.map((pick) => pick.elementId),
      declared,
    ),
    {
      bankTenths: corrections?.bankTenths ?? team.bankTenths,
      teamValueTenths: team.squadValueTenths,
      availableFreeTransfers:
        corrections?.availableFreeTransfers ?? DEFAULT_FREE_TRANSFERS,
      fromEvent,
      sellingPrices,
      assumed,
    },
  );
  return start
    ? {
        status: "ready",
        start,
        event: fromEvent,
        declared,
        source: "published",
      }
    : { status: "failed", reason: "squad_not_recognised" };
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
  const storage = browserStorage();
  const stored = storage ? readDeclaredSquad(storage, entryId, event) : null;
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
  const finances = stored
    ? declaredSquadPlanningValues(stored, event, PLAYERS_BY_ELEMENT_ID)
    : null;
  if ((stored && !finances) || (!opening && !finances)) return null;
  const validation = validateDeclaredSquad(elementIds, PLAYERS_BY_ELEMENT_ID, {
    enforceOpeningBudget: opening,
  });
  if (!validation.valid) return null;

  const start = startFromElementIds(elementIds, {
    bankTenths:
      finances?.bankTenths ??
      SQUAD_BUDGET_TENTHS - validation.summary.spentTenths,
    ...(opening ? { teamValueTenths: SQUAD_BUDGET_TENTHS } : {}),
    availableFreeTransfers: finances?.availableFreeTransfers ?? 0,
    fromEvent: event,
    sellingPrices:
      finances?.sellingPrices ??
      new Map(
        validation.summary.players.map((player) => [
          player.id,
          player.priceTenths,
        ]),
      ),
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

function browserStorage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
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
