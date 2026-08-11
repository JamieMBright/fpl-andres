import { beforeEach, describe, expect, it } from "vitest";

import {
  ANALYTICS_STORAGE_KEY,
  analyticsPath,
  disableAnalytics,
  enableAnalytics,
  readAnalyticsConsent,
  recordPageView,
} from "./analytics-consent";

const MEASUREMENT_ID = "G-ABC123DEF4";

beforeEach(() => {
  localStorage.clear();
  document
    .querySelectorAll('script[data-fpl-andres-analytics="true"]')
    .forEach((element) => element.remove());
  delete window.dataLayer;
});

describe("analytics consent boundary", () => {
  it("does not load Google before explicit consent", () => {
    expect(readAnalyticsConsent(localStorage)).toBeNull();
    expect(recordPageView(MEASUREMENT_ID, "/results", localStorage)).toBe(
      false,
    );
    expect(
      document.querySelector('script[src*="googletagmanager"]'),
    ).toBeNull();
    expect(window.dataLayer).toBeUndefined();
  });

  it("rejects malformed measurement IDs", () => {
    expect(enableAnalytics("UA-123", localStorage)).toBe(false);
    expect(localStorage.getItem(ANALYTICS_STORAGE_KEY)).toBeNull();
    expect(
      document.querySelector('script[src*="googletagmanager"]'),
    ).toBeNull();
  });

  it("loads GA once after consent and records a sanitized page path", () => {
    expect(enableAnalytics(MEASUREMENT_ID, localStorage)).toBe(true);
    expect(readAnalyticsConsent(localStorage)).toBe("granted");
    expect(
      document.querySelectorAll('script[src*="googletagmanager"]'),
    ).toHaveLength(1);

    expect(
      recordPageView(MEASUREMENT_ID, "/plan?team=212279", localStorage),
    ).toBe(true);
    expect(
      recordPageView(MEASUREMENT_ID, "/plan?team=999999", localStorage),
    ).toBe(true);
    expect(
      document.querySelectorAll('script[src*="googletagmanager"]'),
    ).toHaveLength(1);

    expect(window.dataLayer).toContainEqual([
      "event",
      "page_view",
      {
        page_location: "https://fpl-andres.vercel.app/plan",
        page_path: "/plan",
        page_referrer: "",
        page_title: "FPL Andres",
      },
    ]);
    const serialized = JSON.stringify(window.dataLayer);
    expect(serialized).not.toContain("212279");
    expect(serialized).not.toContain("999999");
  });

  it("redacts identifiers embedded in team routes", () => {
    expect(analyticsPath("/team/212279?from=home")).toBe("/team/:teamId");
    expect(analyticsPath("/players?sort=price#midfielders")).toBe("/players");
  });

  it("stops future events when consent is revoked", () => {
    enableAnalytics(MEASUREMENT_ID, localStorage);
    document.cookie = "_ga=test-client; path=/";
    document.cookie = "_ga_ABC123DEF4=test-session; path=/";
    disableAnalytics(MEASUREMENT_ID, localStorage);

    expect(readAnalyticsConsent(localStorage)).toBe("denied");
    expect(recordPageView(MEASUREMENT_ID, "/results", localStorage)).toBe(
      false,
    );
    expect(window["ga-disable-G-ABC123DEF4"]).toBe(true);
    expect(document.cookie).not.toContain("_ga=");
    expect(document.cookie).not.toContain("_ga_ABC123DEF4=");
  });

  it("restores Google's consent state when analytics is enabled again", () => {
    enableAnalytics(MEASUREMENT_ID, localStorage);
    disableAnalytics(MEASUREMENT_ID, localStorage);
    enableAnalytics(MEASUREMENT_ID, localStorage);

    expect(window.dataLayer).toContainEqual([
      "consent",
      "update",
      { analytics_storage: "granted" },
    ]);
    const consentUpdates = window.dataLayer?.filter(
      (entry) => entry[0] === "consent" && entry[1] === "update",
    );
    expect(consentUpdates?.at(-1)).toEqual([
      "consent",
      "update",
      { analytics_storage: "granted" },
    ]);
    expect(window["ga-disable-G-ABC123DEF4"]).toBe(false);
  });
});
