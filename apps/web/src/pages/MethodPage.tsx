import { MethodFlow } from "../components/MethodFlow";
import { Methodology } from "../components/Methodology";
import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

export default function MethodPage() {
  useDocumentTitle(
    "Method",
    "Every scoring route, every parameter and every limit behind the FPL Andres projection.",
    { canonicalPath: "/methodology" },
  );
  return (
    <section className="text-page method-page">
      <p className="eyebrow">Method</p>
      <RouteHeading>How the projection is built.</RouteHeading>
      <MethodFlow />
      <Methodology />
    </section>
  );
}
