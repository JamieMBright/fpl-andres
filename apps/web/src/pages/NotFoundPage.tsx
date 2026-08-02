import { Link } from "react-router-dom";

import { RouteHeading } from "../components/RouteHeading";

export default function NotFoundPage() {
  return (
    <section className="text-page">
      <p className="eyebrow">Wrong turn</p>
      <RouteHeading>Nothing here.</RouteHeading>
      <p>That page doesn&rsquo;t exist. Let&rsquo;s start again.</p>
      <Link className="text-command" to="/">
        Back to the Team ID
      </Link>
    </section>
  );
}
