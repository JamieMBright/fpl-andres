import { MethodFlow } from "../components/MethodFlow";
import { Methodology } from "../components/Methodology";
import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

export default function MethodPage() {
  useDocumentTitle(
    "How I work",
    "Every scoring route, every parameter and every limit behind the FPL Andres projection.",
  );
  return (
    <section className="text-page method-page">
      <p className="eyebrow">Method</p>
      <RouteHeading>How I work.</RouteHeading>
      <MethodFlow />
      <Methodology />
    </section>
  );
}
