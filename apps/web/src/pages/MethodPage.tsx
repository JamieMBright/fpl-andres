import { Methodology } from "../components/Methodology";
import { RouteHeading } from "../components/RouteHeading";

export default function MethodPage() {
  return (
    <section className="text-page method-page">
      <p className="eyebrow">Method</p>
      <RouteHeading>How I work.</RouteHeading>
      <Methodology />
    </section>
  );
}
