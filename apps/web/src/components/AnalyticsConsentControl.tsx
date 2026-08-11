import { useState } from "react";

import {
  disableAnalytics,
  enableAnalytics,
  readAnalyticsConsent,
  recordPageView,
} from "../state/analytics-consent";

export function AnalyticsConsentControl({
  measurementId,
}: {
  readonly measurementId: string;
}) {
  const configured = /^G-[A-Z0-9]{6,20}$/.test(measurementId);
  const [consent, setConsent] = useState(() =>
    readAnalyticsConsent(window.localStorage),
  );

  if (!configured) {
    return (
      <p role="status">
        Optional analytics is not configured. No analytics script loads.
      </p>
    );
  }

  const enabled = consent === "granted";
  return (
    <div>
      <p role="status">Optional analytics is {enabled ? "on" : "off"}.</p>
      <button
        className="secondary-command"
        onClick={() => {
          if (enabled) {
            disableAnalytics(measurementId, window.localStorage);
            setConsent("denied");
          } else if (enableAnalytics(measurementId, window.localStorage)) {
            setConsent("granted");
            recordPageView(
              measurementId,
              `${window.location.pathname}${window.location.search}`,
              window.localStorage,
            );
          }
        }}
        type="button"
      >
        {enabled ? "Turn optional analytics off" : "Allow optional analytics"}
      </button>
    </div>
  );
}
