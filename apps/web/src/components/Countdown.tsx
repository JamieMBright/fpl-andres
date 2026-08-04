import { deadlineDay } from "../format";

/**
 * How long until the deadline, as the last cell of the index bar.
 *
 * Read once at module load rather than on a timer: this is a page that gets
 * refreshed, not watched, and a ticking clock would re-render the whole shell
 * every second to move a number that changes once a day.
 */
const LOADED_AT = Date.now();

export function Countdown({ deadline }: { deadline: string }) {
  const kickoff = new Date(deadline);
  const days = Math.max(
    0,
    Math.ceil((kickoff.getTime() - LOADED_AT) / 86_400_000),
  );

  return (
    <span className="teletext-countdown">
      GW1 {deadlineDay.format(kickoff)}
      {days === 0 ? " · TODAY" : ` · ${String(days)}D`}
    </span>
  );
}
