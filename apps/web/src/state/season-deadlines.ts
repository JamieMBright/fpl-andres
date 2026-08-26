import artifact from "../data/deadlines.json";

export interface SeasonDeadline {
  event: number;
  deadline: string;
  finished: boolean;
}

export const FULL_SEASON_DEADLINES =
  artifact.deadlines as readonly SeasonDeadline[];

export function planningEventAt(now: Date = new Date()): number {
  const upcoming = FULL_SEASON_DEADLINES.find(
    (row) => Date.parse(row.deadline) > now.getTime(),
  );
  return upcoming?.event ?? FULL_SEASON_DEADLINES.at(-1)?.event ?? 1;
}

export function nextDeadlineAt(now: Date = new Date()): SeasonDeadline | null {
  return (
    FULL_SEASON_DEADLINES.find(
      (row) => Date.parse(row.deadline) > now.getTime(),
    ) ?? null
  );
}

export function deadlineAfterEvent(event: number): SeasonDeadline | null {
  return FULL_SEASON_DEADLINES.find((row) => row.event > event) ?? null;
}
