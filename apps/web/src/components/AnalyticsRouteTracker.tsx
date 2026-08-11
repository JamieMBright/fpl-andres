import { useEffect } from "react";
import { useLocation } from "react-router-dom";

export function AnalyticsRouteTracker({
  measurementId,
}: {
  readonly measurementId: string;
}) {
  const { pathname, search } = useLocation();

  useEffect(() => {
    void import("../state/analytics-consent").then(({ recordPageView }) => {
      recordPageView(
        measurementId,
        `${pathname}${search}`,
        window.localStorage,
      );
    });
  }, [measurementId, pathname, search]);

  return null;
}
