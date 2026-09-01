import { CHIPS, type Chip } from "./declared-chips";

/**
 * How much of the cohort has spent each chip, cumulatively, gameweek by
 * gameweek.
 *
 * A chip is a once-a-half resource, and the aggregate published per gameweek
 * only ever says who is spending it *this* week. Summing that across the
 * gameweeks captured so far turns "who spent it this week" into "who has
 * spent it by now", which is the curve a manager actually wants: a wildcard
 * window shows up as the week the line jumps, not as a bar that resets to
 * zero the week after.
 *
 * The counter restarts at gameweek 20, because that is the same restart FPL
 * gives every manager: a first-half wildcard and a second-half wildcard are
 * different resources, and a cohort that is 80% through its first Bench Boost
 * has spent none of its second.
 */

export const SECOND_HALF_START = 20;

export interface ChipAdoptionPoint {
  event: number;
  /** Share of the sampled cohort that has played this chip at least once this half. */
  share: number;
}

export interface ChipAdoptionSeries {
  chip: Chip;
  points: ChipAdoptionPoint[];
}

export interface PortfolioSampleLike {
  attempted: number;
  aggregate?: { chips: Record<string, number> };
}

export interface PortfolioSeriesLike {
  events: readonly number[];
  samples: Record<string, PortfolioSampleLike>;
}

function sampleKey(event: number): string {
  return String(event).padStart(2, "0");
}

/** Every chip series, one point per captured gameweek, in event order. */
export function chipAdoption(
  series: PortfolioSeriesLike,
): ChipAdoptionSeries[] {
  const events = [...series.events].sort((left, right) => left - right);
  const cumulative = new Map<Chip, number>(CHIPS.map((chip) => [chip, 0]));
  const points = new Map<Chip, ChipAdoptionPoint[]>(
    CHIPS.map((chip) => [chip, []]),
  );
  let halfStartSeen = false;

  for (const event of events) {
    if (event >= SECOND_HALF_START && !halfStartSeen) {
      halfStartSeen = true;
      for (const chip of CHIPS) cumulative.set(chip, 0);
    }
    const sample = series.samples[sampleKey(event)];
    const attempted = sample?.attempted ?? 0;
    const thisWeek = sample?.aggregate?.chips ?? {};
    for (const chip of CHIPS) {
      const spent = (cumulative.get(chip) ?? 0) + (thisWeek[chip] ?? 0);
      cumulative.set(chip, spent);
      points.get(chip)?.push({
        event,
        share: attempted > 0 ? spent / attempted : 0,
      });
    }
  }

  return CHIPS.map((chip) => ({ chip, points: points.get(chip) ?? [] }));
}
