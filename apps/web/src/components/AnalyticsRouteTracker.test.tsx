import { render } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { ANALYTICS_STORAGE_KEY } from "../state/analytics-consent";
import { AnalyticsRouteTracker } from "./AnalyticsRouteTracker";

const MEASUREMENT_ID = "G-ABC123DEF4";

function MoveToPrivatePlan() {
  const navigate = useNavigate();
  useEffect(() => {
    void navigate("/plan?team=212279");
  }, [navigate]);
  return null;
}

beforeEach(() => {
  localStorage.clear();
  document
    .querySelectorAll('script[data-fpl-andres-analytics="true"]')
    .forEach((element) => element.remove());
  delete window.dataLayer;
});

describe("analytics route tracker", () => {
  it("records sanitized route changes only after consent", async () => {
    localStorage.setItem(ANALYTICS_STORAGE_KEY, "granted");
    render(
      <MemoryRouter initialEntries={["/results"]}>
        <AnalyticsRouteTracker measurementId={MEASUREMENT_ID} />
        <MoveToPrivatePlan />
      </MemoryRouter>,
    );

    await expect.poll(() => window.dataLayer?.length ?? 0).toBeGreaterThan(4);
    const serialized = JSON.stringify(window.dataLayer);
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
    expect(serialized).toContain('"page_path":"/plan"');
    expect(serialized).not.toContain("212279");
  });
});
