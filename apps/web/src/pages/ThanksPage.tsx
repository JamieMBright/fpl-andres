import { Link, useSearchParams } from "react-router-dom";

import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

const CONTACT_CONTEXT = "contact";

export default function ThanksPage() {
  const [searchParams] = useSearchParams();
  const isContact = searchParams.get("from") === CONTACT_CONTEXT;

  useDocumentTitle(
    "Thank you",
    "Continue planning your FPL season or inspect how FPL Andres reaches each recommendation.",
    { canonicalPath: null, robots: "noindex, nofollow" },
  );

  return (
    <section className="text-page">
      <p className="eyebrow">Complete</p>
      <RouteHeading>Thank you</RouteHeading>
      {isContact ? (
        <>
          <h2>Your message is on its way.</h2>
          <p>I aim to reply within two working days.</p>
        </>
      ) : (
        <p>You&rsquo;re all set. Pick up where you need me.</p>
      )}
      <p>
        <Link className="text-command" to="/plan">
          Plan my season
        </Link>{" "}
        <Link className="text-command" to="/methodology">
          Check the method
        </Link>
      </p>
    </section>
  );
}
