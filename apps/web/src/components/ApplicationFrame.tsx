import { Link, NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";

import { FIRST_DEADLINE_2026_27 } from "../public-ids";
import { AnalyticsRouteTracker } from "./AnalyticsRouteTracker";
import { BielsaBucket } from "./BielsaBucket";
import { Countdown } from "./Countdown";
import { MobilePlanCta } from "./MobilePlanCta";
import { OfflineBanner } from "./OfflineBanner";

/**
 * The shell every route renders inside: skip link, header, theme, footer.
 *
 * Theme state lives here rather than in a context because
 * exactly one control reads it and exactly one element consumes it -- the
 * `data-theme` attribute on the document -- and a context for a single
 * consumer is indirection with no payoff.
 */

const SOCIAL_LINKS = [
  {
    name: "X",
    href: "https://x.com/fpl_andres",
    path: "M18.9 2H22l-7.3 8.3L23 22h-6.6l-5.2-6.8L5.3 22H2.2l7.8-8.9L1.7 2h6.8l4.7 6.2zm-1.1 18h1.7L7.3 3.7H5.5z",
  },
  {
    name: "Reddit",
    href: "https://reddit.com/user/fpl_andres",
    path: "M22 12a2 2 0 0 0-3.4-1.4 10 10 0 0 0-5.1-1.6l.9-4.1 2.9.6a1.7 1.7 0 1 0 .2-1l-3.4-.7a.5.5 0 0 0-.6.4l-1 4.8a10 10 0 0 0-5.2 1.6A2 2 0 1 0 4.6 14a4 4 0 0 0 0 .6c0 3 3.4 5.4 7.5 5.4s7.4-2.4 7.4-5.4a4 4 0 0 0 0-.6A2 2 0 0 0 22 12M7.5 13.4a1.4 1.4 0 1 1 1.4 1.4 1.4 1.4 0 0 1-1.4-1.4m7.7 4a5 5 0 0 1-3.1.9 5 5 0 0 1-3.2-.9.4.4 0 0 1 .5-.6 4.2 4.2 0 0 0 2.7.7 4.2 4.2 0 0 0 2.6-.7.4.4 0 1 1 .5.6m-.2-2.6a1.4 1.4 0 1 1 1.4-1.4 1.4 1.4 0 0 1-1.4 1.4",
  },
  {
    name: "Instagram",
    href: "https://instagram.com/fpl_andres",
    path: "M12 2.2c3.2 0 3.6 0 4.9.1 3.3.1 4.8 1.7 5 5 0 1.3.1 1.6.1 4.7s0 3.5-.1 4.8c-.2 3.3-1.7 4.9-5 5-1.3.1-1.7.1-4.9.1s-3.6 0-4.9-.1c-3.3-.1-4.8-1.7-5-5C2 15.5 2 15.1 2 12s0-3.4.1-4.7c.2-3.3 1.7-4.9 5-5C8.4 2.2 8.8 2.2 12 2.2m0 5.1A4.7 4.7 0 1 0 16.7 12 4.7 4.7 0 0 0 12 7.3m0 7.7A3 3 0 1 1 15 12a3 3 0 0 1-3 3m4.9-8.9a1.1 1.1 0 1 0 1.1 1.1 1.1 1.1 0 0 0-1.1-1.1",
  },
  {
    name: "TikTok",
    href: "https://tiktok.com/@fpl_andres",
    path: "M16.6 2h-3v13.1a2.4 2.4 0 1 1-2.4-2.4c.2 0 .4 0 .6.1V9.7h-.6a5.4 5.4 0 1 0 5.4 5.4V8.6a6.2 6.2 0 0 0 3.6 1.2V6.8a3.4 3.4 0 0 1-3.6-3.3z",
  },
  {
    name: "YouTube",
    href: "https://youtube.com/@fpl_andres",
    path: "M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4a2.5 2.5 0 0 0-1.8 1.8A26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8C5.8 19 12 19 12 19s6.2 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8M10 15V9l5.2 3z",
  },
] as const;

/** `dark` is the green and blue Third Kit; it is the default. */
type ThemeName = "light" | "away" | "dark";

/** Home, Away, Third, then round again. */
const NEXT_KIT: Record<ThemeName, ThemeName> = {
  light: "away",
  away: "dark",
  dark: "light",
};

/** The control names the kit currently being worn. */
const KIT_LABEL: Record<ThemeName, string> = {
  light: "Home Kit",
  away: "Away Kit",
  dark: "Third Kit",
};

const THEME_STORAGE_KEY = "fpl-andres:theme";

function readStoredTheme(): ThemeName {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "away") return stored;
    if (stored === "third") return "away";
    return "dark";
  } catch {
    // A blocked storage partition must not stop the page rendering.
    return "dark";
  }
}

export function ApplicationFrame() {
  const [theme, setTheme] = useState<ThemeName>(readStoredTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Preference is cosmetic; failing to persist it is not an error.
    }
  }, [theme]);

  return (
    <div className="app-shell">
      <AnalyticsRouteTracker
        measurementId={import.meta.env.VITE_GOOGLE_ANALYTICS_ID ?? ""}
      />
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <OfflineBanner />
      <header className="site-header">
        <Link aria-label="FPL Andres home" className="brand" to="/">
          <BielsaBucket />
          <span className="brand-words">
            <strong translate="no">FPL Andres</strong>
            <small>Analysis, not opinion</small>
          </span>
        </Link>
        <div className="header-controls">
          <Countdown deadline={FIRST_DEADLINE_2026_27} />
          <button
            className="theme-toggle"
            onClick={() => {
              setTheme(NEXT_KIT[theme]);
            }}
            type="button"
          >
            {KIT_LABEL[theme]}
          </button>
        </div>
      </header>
      <nav aria-label="Primary navigation" className="teletext-strip">
        <NavLink to="/plan">Plan</NavLink>
        <NavLink to="/players">Players</NavLink>
        <NavLink to="/analysis">Analysis</NavLink>
        <NavLink to="/fpl500">FPL500</NavLink>
        <NavLink to="/methodology">Method</NavLink>
        <NavLink to="/results">Results</NavLink>
        <NavLink className="teletext-strip-half" to="/faq">
          FAQ
        </NavLink>
        <NavLink
          className="teletext-strip-half teletext-strip-about"
          to="/about"
        >
          About
        </NavLink>
      </nav>
      <main id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="site-footer">
        <nav aria-label="Site map" className="site-map">
          <h2>Site map</h2>
          <ul>
            <li>
              <Link to="/plan">Plan</Link>
            </li>
            <li>
              <Link to="/players">Players</Link>
            </li>
            <li>
              <Link to="/analysis">Analysis</Link>
            </li>
            <li>
              <Link to="/methodology">Method</Link>
            </li>
            <li>
              <Link to="/calibration">Calibration</Link>
            </li>
            <li>
              <Link to="/results">Results</Link>
            </li>
            <li>
              <Link to="/fpl500">FPL500</Link>
            </li>
            <li>
              <Link to="/faq">FAQ</Link>
            </li>
            <li>
              <Link to="/about">About</Link>
            </li>
            <li>
              <Link to="/privacy">Privacy</Link>
            </li>
            <li>
              <Link to="/expected-xi">Expected XI</Link>
            </li>
            <li>
              <Link to="/markets">Markets</Link>
            </li>
            <li>
              <Link to="/kits">Kits</Link>
            </li>
          </ul>
        </nav>
        <div className="site-footer-end">
          <ul className="social-links">
            {SOCIAL_LINKS.map((social) => (
              <li key={social.name}>
                <a
                  aria-label={`FPL Andres on ${social.name}`}
                  href={social.href}
                  rel="me noopener noreferrer"
                  target="_blank"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d={social.path} />
                  </svg>
                </a>
              </li>
            ))}
          </ul>
          <p>
            Independent analysis. Not affiliated with Fantasy Premier League.
          </p>
        </div>
      </footer>
      <MobilePlanCta />
    </div>
  );
}
