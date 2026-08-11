import { siteUrl } from "../site";

export const ANALYTICS_STORAGE_KEY = "fpl-andres:analytics-consent:v1";

type AnalyticsConsent = "granted" | "denied";

declare global {
  interface Window {
    dataLayer?: unknown[][];
    [key: `ga-disable-${string}`]: boolean | undefined;
  }
}

function validMeasurementId(measurementId: string): boolean {
  return /^G-[A-Z0-9]{6,20}$/.test(measurementId);
}

function push(...values: unknown[]): void {
  window.dataLayer ??= [];
  window.dataLayer.push(values);
}

function loadAnalytics(measurementId: string): void {
  window[`ga-disable-${measurementId}`] = false;
  push("consent", "update", { analytics_storage: "granted" });
  if (
    document.querySelector<HTMLScriptElement>(
      'script[data-fpl-andres-analytics="true"]',
    )
  ) {
    return;
  }

  const script = document.createElement("script");
  script.async = true;
  script.dataset.fplAndresAnalytics = "true";
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.append(script);

  push("js", new Date());
  push("config", measurementId, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    page_location: siteUrl("/"),
    page_referrer: "",
    send_page_view: false,
  });
}

function clearAnalyticsCookies(): void {
  const names = document.cookie
    .split(";")
    .map((entry) => entry.trim().split("=", 1)[0])
    .filter(
      (name): name is string =>
        name === "_ga" || name?.startsWith("_ga_") === true,
    );
  for (const name of names) {
    for (const domain of ["", location.hostname, `.${location.hostname}`]) {
      document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax${domain ? `; domain=${domain}` : ""}`;
    }
  }
}

export function analyticsPath(path: string): string {
  const pathname = path.split(/[?#]/, 1)[0] || "/";
  return pathname.replace(/^\/team\/[^/]+/, "/team/:teamId");
}

export function readAnalyticsConsent(
  storage: Pick<Storage, "getItem">,
): AnalyticsConsent | null {
  try {
    const stored = storage.getItem(ANALYTICS_STORAGE_KEY);
    return stored === "granted" || stored === "denied" ? stored : null;
  } catch {
    return null;
  }
}

export function enableAnalytics(
  measurementId: string,
  storage: Pick<Storage, "setItem">,
): boolean {
  if (!validMeasurementId(measurementId)) return false;
  try {
    storage.setItem(ANALYTICS_STORAGE_KEY, "granted");
  } catch {
    return false;
  }
  loadAnalytics(measurementId);
  return true;
}

export function disableAnalytics(
  measurementId: string,
  storage: Pick<Storage, "setItem">,
): void {
  try {
    storage.setItem(ANALYTICS_STORAGE_KEY, "denied");
  } catch {
    // A blocked storage partition still gets the in-memory disable flag.
  }
  if (!validMeasurementId(measurementId)) return;
  window[`ga-disable-${measurementId}`] = true;
  clearAnalyticsCookies();
  if (window.dataLayer) {
    push("consent", "update", { analytics_storage: "denied" });
  }
}

export function recordPageView(
  measurementId: string,
  path: string,
  storage: Pick<Storage, "getItem">,
): boolean {
  if (
    !validMeasurementId(measurementId) ||
    readAnalyticsConsent(storage) !== "granted"
  ) {
    return false;
  }
  loadAnalytics(measurementId);
  const pagePath = analyticsPath(path);
  push("event", "page_view", {
    page_location: siteUrl(pagePath),
    page_path: pagePath,
    page_referrer: "",
    page_title: "FPL Andres",
  });
  return true;
}
