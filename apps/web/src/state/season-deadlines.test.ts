import { describe, expect, it } from "vitest";

import {
  deadlineAfterEvent,
  FULL_SEASON_DEADLINES,
  nextDeadlineAt,
  planningEventAt,
} from "./season-deadlines";

describe("season deadline ledger", () => {
  it("keeps historical event boundaries after planning inputs advance", () => {
    expect(planningEventAt(new Date("2026-08-21T17:29:59Z"))).toBe(1);
    expect(planningEventAt(new Date("2026-08-21T17:30:00Z"))).toBe(2);
    expect(deadlineAfterEvent(1)?.event).toBe(2);
  });

  it("has no next deadline after the season ends", () => {
    const final = FULL_SEASON_DEADLINES.at(-1);
    expect(final).toBeDefined();
    const after = new Date(Date.parse(final!.deadline) + 1);

    expect(nextDeadlineAt(after)).toBeNull();
    expect(planningEventAt(after)).toBe(final!.event);
  });
});
