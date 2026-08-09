import { useEffect, useState } from "react";

/**
 * Minutes to the next deadline, as a teletext clock beside the kit button.
 *
 * It ticks, unlike the version that read the clock once at module load: a
 * countdown that never moves is a label. Only this component re-renders, and
 * only once a minute, which is the resolution it prints.
 */

const MINUTE = 60_000;

/** Green while there is time, amber inside two days, red inside six hours. */
function urgencyOf(minutes: number): "calm" | "near" | "now" {
  if (minutes <= 6 * 60) return "now";
  if (minutes <= 48 * 60) return "near";
  return "calm";
}

function faceOf(minutes: number): string {
  if (minutes <= 0) return "GONE";
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const rest = minutes % 60;
  if (days > 0) return `${String(days)}d ${String(hours)}h ${String(rest)}m`;
  if (hours > 0) return `${String(hours)}h ${String(rest)}m`;
  return `${String(rest)}m`;
}

export function Countdown({ deadline }: { deadline: string }) {
  const kickoff = new Date(deadline).getTime();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const tick = setInterval(() => {
      setNow(Date.now());
    }, MINUTE);
    return () => {
      clearInterval(tick);
    };
  }, []);

  const minutes = Math.max(0, Math.ceil((kickoff - now) / MINUTE));

  return (
    <span className={`teletext-countdown is-${urgencyOf(minutes)}`}>
      <svg aria-hidden="true" className="countdown-clock" viewBox="0 0 16 16">
        <rect
          fill="none"
          height="13"
          stroke="currentColor"
          strokeWidth="1.5"
          width="13"
          x="1.5"
          y="1.5"
        />
        <path
          d="M8 4.5 V8 H11"
          fill="none"
          stroke="currentColor"
          strokeLinecap="square"
          strokeWidth="1.5"
        />
      </svg>
      <span className="visually-hidden">Next deadline in </span>
      {faceOf(minutes)}
    </span>
  );
}
