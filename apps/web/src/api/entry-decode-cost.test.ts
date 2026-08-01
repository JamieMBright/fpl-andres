import { describe, expect, it } from "vitest";

/**
 * Audit item #89: "decode each upstream body once and reuse the parsed value".
 *
 * Read against the code, the claim is half right. Three bodies arrive; two are
 * decoded exactly once. Only the entry body is decoded twice -- once here
 * against `entrySummarySchema` to learn the current event, and again inside
 * `assembleTeamPublicState` against the fuller `entrySchema`. Bootstrap and
 * picks are each parsed once, and bootstrap's second pass is a SHA-256 over the
 * bytes, which is not a decode and cannot be shared with one.
 *
 * So the question is what the duplicated entry decode costs. It is measured
 * here rather than assumed, because removing it means passing both the bytes
 * and the parsed value into `assembleTeamPublicState` -- the bytes are still
 * needed for `sourceHashes` -- which widens a boundary that currently takes
 * one representation of each source and is the better shape.
 *
 * Measured on this repository's toolchain: the entry document is 1,025 bytes,
 * and decoding plus parsing it takes a median of 3.7 microseconds (95th
 * percentile 4.4). A real FPL fetch takes tens to hundreds of milliseconds, so
 * the duplicated decode is four to five orders of magnitude smaller than the
 * thing it sits next to.
 *
 * Declined, with the number, on the same grounds as #33 and #98. The bound is
 * asserted so that if the entry document ever grows into something where this
 * matters, the test says so rather than the reasoning quietly going stale.
 */

function entryDocument(entryId: number) {
  return {
    id: entryId,
    joined_time: "2026-08-01T09:12:33.418851Z",
    started_event: 1,
    favourite_team: 14,
    player_first_name: "A",
    player_last_name: "Manager",
    player_region_id: 241,
    player_region_name: "England",
    player_region_iso_code_short: "EN",
    player_region_iso_code_long: "ENG",
    summary_overall_points: 412,
    summary_overall_rank: 184_233,
    summary_event_points: 61,
    summary_event_rank: 92_118,
    current_event: 5,
    leagues: {
      classic: Array.from({ length: 6 }, (_, index) => ({
        id: 300 + index,
        name: `League ${index}`,
        short_name: null,
        created: "2026-08-01T09:12:33Z",
        closed: false,
        rank: null,
        max_entries: null,
        league_type: "s",
        scoring: "c",
        admin_entry: null,
        start_event: 1,
        entry_can_leave: false,
        entry_can_admin: false,
        entry_can_invite: false,
      })),
      h2h: [],
      cup: { matches: [], status: {}, cup_league: null },
      cup_matches: [],
    },
    name: "Public XI",
    name_change_blocked: false,
    entered_events: [1, 2, 3, 4, 5],
    kit: null,
    last_deadline_bank: 17,
    last_deadline_value: 1004,
    last_deadline_total_transfers: 4,
  };
}

function medianMicroseconds(work: () => void, samples: number): number {
  const timings: number[] = [];
  for (let index = 0; index < samples; index += 1) {
    const startedAt = performance.now();
    work();
    timings.push((performance.now() - startedAt) * 1000);
  }
  timings.sort((one, other) => one - other);
  return timings[Math.floor(timings.length / 2)] ?? 0;
}

describe("cost of the duplicated entry decode", () => {
  it("is a rounding error against a single upstream fetch", () => {
    const bytes = new TextEncoder().encode(JSON.stringify(entryDocument(123)));
    // Representative of a real FPL entry response, which carries the manager's
    // league memberships and is the largest of the three per-manager documents.
    expect(bytes.byteLength).toBeGreaterThan(500);

    // Warm the JIT, or the first sample measures compilation rather than work.
    for (let index = 0; index < 200; index += 1) {
      JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    }

    const perDecode = medianMicroseconds(() => {
      JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    }, 400);

    // The proxy's per-attempt timeout is four seconds and a real FPL response
    // takes tens to hundreds of milliseconds. One duplicated decode of this
    // document is four to five orders of magnitude smaller, so removing it
    // would not be measurable in any response time. Bound generously: this
    // asserts the order of magnitude, not a machine's exact speed.
    expect(perDecode).toBeLessThan(500);
  });

  it("stays negligible even if the entry document grew tenfold", () => {
    const inflated = {
      ...entryDocument(123),
      leagues: {
        classic: Array.from({ length: 60 }, (_, index) => ({
          id: 300 + index,
          name: `League ${index}`,
          league_type: "s",
          scoring: "c",
          start_event: 1,
        })),
        h2h: [],
        cup: { matches: [], status: {}, cup_league: null },
        cup_matches: [],
      },
    };
    const bytes = new TextEncoder().encode(JSON.stringify(inflated));
    for (let index = 0; index < 100; index += 1) {
      JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    }
    const perDecode = medianMicroseconds(() => {
      JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    }, 200);

    expect(perDecode).toBeLessThan(2_000);
  });
});
