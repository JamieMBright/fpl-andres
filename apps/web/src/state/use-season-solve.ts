import { useEffect, useState } from "react";

import type { SolvedGameweek, SolveStart } from "./season-solver";

/**
 * Runs the season solve in a worker and hands back gameweeks as they arrive.
 *
 * `progress` is deliberately separate from `gameweeks.length`: a plan starting
 * at gameweek 12 has 27 to solve, not 38, and a progress bar that implies
 * otherwise is a lie about how much waiting is left.
 */

export type SolveStatus = "idle" | "solving" | "done" | "failed";

export interface SeasonSolve {
  status: SolveStatus;
  gameweeks: SolvedGameweek[];
  /** 0 to 1, or null when there is nothing being solved. */
  progress: number | null;
  reason: string | null;
}

type WorkerMessage =
  | { type: "gameweek"; week: SolvedGameweek }
  | { type: "done" }
  | { type: "failed"; reason: string };

const LAST_EVENT = 38;

interface Accumulated {
  gameweeks: SolvedGameweek[];
  finished: boolean;
  reason: string | null;
}

const EMPTY: Accumulated = { gameweeks: [], finished: false, reason: null };

export function useSeasonSolve(start: SolveStart | null): SeasonSolve {
  const [results, setResults] = useState<Accumulated>(EMPTY);
  const [solvedFor, setSolvedFor] = useState<SolveStart | null>(null);

  // Reset during render rather than in an effect: a new start must not spend a
  // frame showing the previous manager's gameweeks.
  if (start !== solvedFor) {
    setSolvedFor(start);
    setResults(EMPTY);
  }

  useEffect(() => {
    if (!start) return;

    const worker = new Worker(
      new URL("../workers/season-solver.worker.ts", import.meta.url),
      { type: "module" },
    );

    worker.onmessage = ({ data }: MessageEvent<WorkerMessage>) => {
      if (data.type === "gameweek") {
        setResults((previous) => ({
          ...previous,
          gameweeks: [...previous.gameweeks, data.week],
        }));
        return;
      }
      if (data.type === "done") {
        setResults((previous) => ({ ...previous, finished: true }));
        return;
      }
      setResults((previous) => ({ ...previous, reason: data.reason }));
    };

    worker.onerror = (event) => {
      setResults((previous) => ({
        ...previous,
        reason: event.message || "the solver stopped",
      }));
    };

    worker.postMessage(start);
    return () => worker.terminate();
  }, [start]);

  if (!start) {
    return { status: "idle", gameweeks: [], progress: null, reason: null };
  }

  const expected = LAST_EVENT - start.fromEvent + 1;
  const status: SolveStatus = results.reason
    ? "failed"
    : results.finished
      ? "done"
      : "solving";

  return {
    status,
    gameweeks: results.gameweeks,
    progress: Math.min(1, results.gameweeks.length / expected),
    reason: results.reason,
  };
}
