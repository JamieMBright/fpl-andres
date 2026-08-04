import { useId } from "react";

/**
 * One track, two thumbs.
 *
 * Two separate sliders stacked vertically ask the reader to hold a range in
 * their head across two controls. This is the same range as one bar, which is
 * how a range actually looks.
 *
 * Built from two real `input[type=range]` elements laid over each other rather
 * than from divs and pointer events: keyboard support, screen-reader value
 * announcements and touch targets all come free, and none of them are free to
 * write by hand. Only the thumbs take pointer events, so whichever one is
 * nearer the click is the one that moves.
 */
export interface RangeSliderProps {
  label: string;
  from: number;
  to: number;
  min: number;
  max: number;
  step: number;
  /** Turns a value into what the reader sees, e.g. "5.0%". */
  format: (value: number) => string;
  onChange: (next: { from: number; to: number }) => void;
}

export function RangeSlider({
  label,
  from,
  to,
  min,
  max,
  step,
  format,
  onChange,
}: RangeSliderProps) {
  const ids = useId();
  const span = max - min || 1;
  const startPercent = ((from - min) / span) * 100;
  const endPercent = ((to - min) / span) * 100;

  return (
    <div className="range-slider">
      <p className="range-slider-value mono">
        {format(from)} – {format(to)}
      </p>
      <div
        className="range-slider-track"
        style={{
          // The filled section is the part of the range that is selected.
          ["--range-start" as string]: `${String(startPercent)}%`,
          ["--range-end" as string]: `${String(endPercent)}%`,
        }}
      >
        <span aria-hidden="true" className="range-slider-fill" />
        <input
          aria-label={`${label}, lowest`}
          id={`${ids}-from`}
          max={max}
          min={min}
          onChange={(event) =>
            onChange({ from: Math.min(Number(event.target.value), to), to })
          }
          step={step}
          type="range"
          value={from}
        />
        <input
          aria-label={`${label}, highest`}
          id={`${ids}-to`}
          max={max}
          min={min}
          onChange={(event) =>
            onChange({ from, to: Math.max(Number(event.target.value), from) })
          }
          step={step}
          type="range"
          value={to}
        />
      </div>
    </div>
  );
}
