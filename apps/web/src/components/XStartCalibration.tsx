import { percent } from "../format";
import { XSTART_VALIDATION } from "../state/xstart-validation";

export function XStartCalibration() {
  const validation = XSTART_VALIDATION;
  return (
    <section
      aria-labelledby="xstart-calibration-title"
      className="xstart-calibration"
    >
      <p className="eyebrow">
        GW{validation.event} · model {validation.modelVersion}
      </p>
      <h2 id="xstart-calibration-title">xStart reliability</h2>
      <p>
        This grades the P(60+) field that was shipped as xStart. Lower Brier and
        log loss are better; a calibrated band puts forecast and actual on the
        same line.
      </p>

      <div className="xstart-reliability" role="list">
        {validation.reliability.map((band) => (
          <div
            className="xstart-reliability-row"
            key={band.label}
            role="listitem"
          >
            <span className="mono">{band.label}</span>
            <span className="xstart-reliability-track" aria-hidden="true">
              <span
                className="is-forecast"
                style={{ width: `${String(band.meanForecast * 100)}%` }}
              />
              <span
                className="is-actual"
                style={{ width: `${String(band.actualStartRate * 100)}%` }}
              />
            </span>
            <span className="mono">
              {percent.format(band.meanForecast)} /{" "}
              {percent.format(band.actualStartRate)}
            </span>
            <span className="mono">n={band.count}</span>
          </div>
        ))}
      </div>
      <p className="xstart-reliability-key">
        <span className="is-forecast" aria-hidden="true" /> Forecast
        <span className="is-actual" aria-hidden="true" /> Actual starts
      </p>

      <div
        aria-label="Scrollable xStart club scores"
        className="squad-table-wrap"
        role="region"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users need to scroll the all-club score table.
        tabIndex={0}
      >
        <table aria-label="xStart score by club">
          <thead>
            <tr>
              <th scope="col">Club</th>
              <th scope="col">Players</th>
              <th scope="col">Brier</th>
              <th scope="col">Top-11 hits</th>
              <th scope="col">Forecast / actual</th>
            </tr>
          </thead>
          <tbody>
            {validation.clubs.map((club) => (
              <tr key={club.club}>
                <th scope="row" translate="no">
                  {club.club}
                </th>
                <td className="mono">{club.count}</td>
                <td className="mono">{club.brier.toFixed(3)}</td>
                <td className="mono">
                  {club.topElevenHits}/{club.actualStarters}
                </td>
                <td className="mono">
                  {percent.format(club.meanForecast)} /{" "}
                  {percent.format(club.actualStartRate)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
