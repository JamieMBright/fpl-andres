import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { AnalyticsConsentControl } from "../components/AnalyticsConsentControl";
import { RouteHeading } from "../components/RouteHeading";
import { clearPrivateBrowserData } from "../state/private-browser-data";
import { useDocumentTitle } from "../state/use-document-title";

const PRIVATE_REPORT =
  "https://github.com/JamieMBright/fpl-andres/security/advisories/new";

export default function PrivacyPage() {
  const [confirming, setConfirming] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);
  const openButton = useRef<HTMLButtonElement>(null);
  const keepButton = useRef<HTMLButtonElement>(null);
  const clearButton = useRef<HTMLButtonElement>(null);

  useDocumentTitle(
    "Privacy and data",
    "What FPL Andres stores in this browser and on its server, why, and for how long.",
    { canonicalPath: "/privacy" },
  );

  const close = () => {
    setConfirming(false);
    requestAnimationFrame(() => openButton.current?.focus());
  };

  useEffect(() => {
    if (confirming) keepButton.current?.focus();
  }, [confirming]);

  const handleConfirmationKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const first = keepButton.current;
    const last = clearButton.current;
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <section className="text-page privacy-page">
      <p className="eyebrow">Privacy and data</p>
      <RouteHeading>Privacy</RouteHeading>
      <p className="lede">
        There are no accounts, advertising cookies or behavioural profiles.
        Optional visitor analytics stays off unless you explicitly allow it. FPL
        Andres reads public FPL data and keeps the private corrections needed
        for a plan under tight limits.
      </p>

      <div className="privacy-sections">
        <section aria-labelledby="privacy-browser">
          <h2 id="privacy-browser">In this browser</h2>
          <p>
            The declared squad, bank, free transfers, chip state, objective,
            cached public team state, manager history and scorecard stay in this
            browser. They are used to restore the plan on a later visit.
          </p>
          <p>
            The selected kit is a separate appearance preference and is kept
            when team data is cleared.
          </p>
        </section>

        <section aria-labelledby="privacy-server">
          <h2 id="privacy-server">On the server</h2>
          <p>
            When a transfer is declared, the server records the Team ID, season,
            gameweek and swap for operational diagnostics. The copy is
            write-only: it is never read back into the plan and cannot change a
            recommendation.
          </p>
          <p>
            Request diagnostics are deleted after 30 days. A declared transfer
            copy is deleted 7 days after that gameweek&apos;s deadline, with a
            30-day absolute maximum. A daily retention job enforces both limits.
          </p>
        </section>

        <section aria-labelledby="privacy-third-parties">
          <h2 id="privacy-third-parties">Other services</h2>
          <p>
            Team lookups pass through this site to Fantasy Premier League&apos;s
            public API. Fonts load from Google Fonts, and available player
            photographs load from the Premier League media host. Google
            Analytics receives a route-only page view only after explicit
            consent and only when a property is configured. Query strings, Team
            IDs, contact details and team state are never included.
          </p>
          <p>
            If you use the About page contact form, your reply address and
            message pass through Resend and into the private project mailbox.
            They are not written to Supabase or used for marketing. The project
            mailbox copy is deleted within 30 days after the conversation
            closes; Resend retains its processor copy under its own service
            terms unless content storage has been disabled.
          </p>
        </section>

        <section aria-labelledby="privacy-analytics">
          <h2 id="privacy-analytics">Optional analytics</h2>
          <p>
            This helps count which public pages are useful. It does not use
            advertising signals or personalised ads. Consent is stored in this
            browser and can be withdrawn here at any time. When enabled, Google
            Analytics may set first-party measurement cookies. Turning it off
            blocks future events and clears those cookies from this site.
          </p>
          <AnalyticsConsentControl
            measurementId={import.meta.env.VITE_GOOGLE_ANALYTICS_ID ?? ""}
          />
        </section>

        <section aria-labelledby="privacy-control">
          <h2 id="privacy-control">Your control</h2>
          <p>
            Clear the manager and planning records saved by FPL Andres on this
            device. This does not affect FPL, the server&apos;s short automatic
            retention window, the selected kit, or data belonging to another
            site.
          </p>
          <button
            ref={openButton}
            className="danger-command"
            onClick={() => setConfirming(true)}
            type="button"
          >
            Clear Saved Team Data
          </button>

          {confirming ? (
            // The alertdialog owns Escape and the two-button Tab trap. The
            // jsx-a11y rule does not treat that ARIA role as interactive.
            // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
            <div
              aria-labelledby="clear-data-title"
              aria-modal="true"
              className="inline-confirmation"
              onKeyDown={handleConfirmationKeyDown}
              role="alertdialog"
            >
              <strong id="clear-data-title">Clear Saved Team Data?</strong>
              <p>
                The next visit will need the Team ID and private corrections
                again. This cannot be undone.
              </p>
              <div>
                <button
                  ref={keepButton}
                  className="secondary-command"
                  onClick={close}
                  type="button"
                >
                  Keep Team Data
                </button>
                <button
                  ref={clearButton}
                  className="danger-command"
                  onClick={() => {
                    const removed = clearPrivateBrowserData(
                      window.localStorage,
                    );
                    setCleared(removed);
                    setConfirming(false);
                  }}
                  type="button"
                >
                  Clear Team Data Now
                </button>
              </div>
            </div>
          ) : null}

          {cleared !== null ? (
            <p className="privacy-cleared" role="status">
              Saved team data cleared ({cleared} record
              {cleared === 1 ? "" : "s"}).
            </p>
          ) : null}
        </section>

        <section aria-labelledby="privacy-contact">
          <h2 id="privacy-contact">Sensitive questions</h2>
          <p>
            A Team ID is public and proves no identity, so there is no manual
            deletion endpoint that lets one person erase another manager&apos;s
            records. Automatic deletion is the safer control.
          </p>
          <p>
            For a sensitive data or security concern, use the repository&apos;s{" "}
            <a href={PRIVATE_REPORT}>private advisory form</a>. Do not put a
            Team ID or private team state in a public issue.
          </p>
        </section>
      </div>
    </section>
  );
}
