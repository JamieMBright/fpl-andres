import { CohortPanel } from "../components/CohortPanel";
import { RouteHeading } from "../components/RouteHeading";
import { ValidationReport } from "../components/ValidationReport";
import { useDocumentTitle } from "../state/use-document-title";

export default function CalibrationPage() {
  useDocumentTitle(
    "Calibration",
    "Every test run against completed seasons, including the ones the model loses.",
  );
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
