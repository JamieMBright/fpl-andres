import { CohortPanel } from "../components/CohortPanel";
import { RouteHeading } from "../components/RouteHeading";
import { ValidationReport } from "../components/ValidationReport";

export default function CalibrationPage() {
  return (
    <section className="text-page validation-page">
      <p className="eyebrow">Calibration</p>
      <RouteHeading>I keep score on myself.</RouteHeading>
      <p>
        All forecasts are wrong. Some are useful. Below is every test I have run
        against completed seasons, including the ones I lose.
      </p>
      <ValidationReport />
      <CohortPanel />
    </section>
  );
}
