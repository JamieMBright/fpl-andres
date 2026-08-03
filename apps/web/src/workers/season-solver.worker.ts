/// <reference lib="webworker" />

import { solveSeason, type SolveStart } from "../state/season-solver";

/**
 * Runs the season solve off the main thread, posting each gameweek as it lands.
 *
 * The whole reason for the worker is that the solve takes seconds, not
 * milliseconds, and a page that freezes for four seconds is worse than one that
 * fills in as it goes. Posting per gameweek rather than at the end is what lets
 * the first card be on screen while the last is still being thought about.
 */

self.onmessage = (message: MessageEvent<SolveStart>) => {
  try {
    for (const week of solveSeason(message.data)) {
      self.postMessage({ type: "gameweek", week });
    }
    self.postMessage({ type: "done" });
  } catch (error) {
    self.postMessage({
      type: "failed",
      reason: error instanceof Error ? error.message : String(error),
    });
  }
};
