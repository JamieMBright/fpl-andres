import { Fpl500Playbook } from "../components/Fpl500Playbook";
import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

export default function Fpl500Page() {
  useDocumentTitle(
    "FPL500",
    "The five hundred managers worth following, and the fund they have not yet been turned into.",
    { canonicalPath: "/fpl500" },
  );
  return (
    <section className="text-page fpl500-page">
      <p className="eyebrow">The cohort</p>
      <RouteHeading>Five hundred managers worth following.</RouteHeading>
      <p className="faq-lede">Determined statistically, not by perception.</p>
      <Fpl500Playbook />
    </section>
  );
}
