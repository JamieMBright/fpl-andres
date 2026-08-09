import { Fpl500Playbook } from "../components/Fpl500Playbook";
import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

export default function Fpl500Page() {
  useDocumentTitle(
    "FPL500",
    "The five hundred managers worth following, and the fund they have not yet been turned into.",
  );
  return (
    <section className="text-page fpl500-page">
      <p className="eyebrow">The cohort</p>
      <RouteHeading>Five hundred managers worth following.</RouteHeading>
      <p className="faq-lede">
        Found by reading the public register rather than by asking anyone.
        Ranked on sustained finishing, in percentile so seasons of very
        different sizes can be compared. What they collectively own is the
        interesting part, and that part is not built yet.
      </p>
      <Fpl500Playbook />
    </section>
  );
}
