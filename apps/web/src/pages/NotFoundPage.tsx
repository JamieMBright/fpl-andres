import { Link } from "react-router-dom";

import { RouteHeading } from "../components/RouteHeading";
import { useDocumentTitle } from "../state/use-document-title";

export default function NotFoundPage() {
  useDocumentTitle(
    "Page not found",
    "That page does not exist. Return to FPL Andres to continue.",
    { canonicalPath: null, robots: "noindex, nofollow" },
  );

  return (
    <section className="text-page">
      <p className="eyebrow">Wrong turn</p>
      <RouteHeading>Page Not Found</RouteHeading>
      <p>That page doesn&rsquo;t exist. Let&rsquo;s start again.</p>
      <Link className="text-command" to="/">
        Back to the Team ID
      </Link>
    </section>
  );
}
