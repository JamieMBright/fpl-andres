/**
 * A labelled bar, drawn from the numbers a step actually uses.
 *
 * A step that says "the routes are summed" has told the reader nothing they
 * can check. A step that shows the fourteen route contributions as bars, with
 * their signs, can be argued with — which is the only reason this page exists.
 */
export interface Bar {
  label: string;
  value: number;
  /** Printed on the bar. Defaults to the value to two places. */
  shown?: string;
}

function widthOf(value: number, extent: number): string {
  return `${((Math.abs(value) / extent) * 100).toFixed(1)}%`;
}

export function BarChart({
  bars,
  caption,
  unit,
}: {
  bars: readonly Bar[];
  caption: string;
  /** What one unit is, said once, so the bars need no repeated suffix. */
  unit: string;
}) {
  const extent = Math.max(...bars.map((bar) => Math.abs(bar.value)), 0.0001);
  const signed = bars.some((bar) => bar.value < 0);

  return (
    <figure className="method-chart">
      <figcaption>
        {caption} <span className="method-chart-unit">({unit})</span>
      </figcaption>
      <ol className={signed ? "method-bars signed" : "method-bars"}>
        {bars.map((bar) => (
          <li key={bar.label}>
            <span className="method-bar-label">{bar.label}</span>
            <span className="method-bar-track">
              <span
                className={bar.value < 0 ? "method-bar negative" : "method-bar"}
                style={{ width: widthOf(bar.value, extent) }}
              />
            </span>
            <span className="method-bar-value mono">
              {bar.shown ?? bar.value.toFixed(2)}
            </span>
          </li>
        ))}
      </ol>
    </figure>
  );
}
