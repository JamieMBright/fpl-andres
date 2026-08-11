import { Link, useLocation } from "react-router-dom";

export function MobilePlanCta() {
  const { pathname } = useLocation();
  const alreadyAtAction =
    pathname === "/" ||
    pathname === "/plan" ||
    pathname.startsWith("/team/") ||
    pathname === "/thanks";

  if (alreadyAtAction) return null;

  return (
    <div className="mobile-plan-cta">
      <Link to="/#team-id">Analyse my squad</Link>
    </div>
  );
}
