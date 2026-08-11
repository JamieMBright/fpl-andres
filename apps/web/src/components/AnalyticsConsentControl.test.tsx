import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { ANALYTICS_STORAGE_KEY } from "../state/analytics-consent";
import { AnalyticsConsentControl } from "./AnalyticsConsentControl";

const MEASUREMENT_ID = "G-ABC123DEF4";

beforeEach(() => {
  localStorage.clear();
  document
    .querySelectorAll('script[data-fpl-andres-analytics="true"]')
    .forEach((element) => element.remove());
  delete window.dataLayer;
});

describe("analytics control", () => {
  it("says analytics is disabled when no property is configured", () => {
    render(<AnalyticsConsentControl measurementId="" />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Optional analytics is not configured",
    );
    expect(
      screen.queryByRole("button", { name: "Allow optional analytics" }),
    ).not.toBeInTheDocument();
  });

  it("requires a deliberate opt-in and allows revocation", async () => {
    const user = userEvent.setup();
    render(<AnalyticsConsentControl measurementId={MEASUREMENT_ID} />);

    expect(
      document.querySelector('script[src*="googletagmanager"]'),
    ).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Allow optional analytics" }),
    );
    expect(localStorage.getItem(ANALYTICS_STORAGE_KEY)).toBe("granted");
    expect(
      document.querySelector('script[src*="googletagmanager"]'),
    ).not.toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Optional analytics is on",
    );

    await user.click(
      screen.getByRole("button", { name: "Turn optional analytics off" }),
    );
    expect(localStorage.getItem(ANALYTICS_STORAGE_KEY)).toBe("denied");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Optional analytics is off",
    );
  });
});
