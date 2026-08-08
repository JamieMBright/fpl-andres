import { render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OfflineBanner } from "./OfflineBanner";

/**
 * A dropped connection reached the page as "Fantasy Premier
 * League could not be reached", which is both wrong and unhelpful: FPL is
 * fine, the train went into a tunnel. Telling someone a remote service is down
 * when their own connection is gone sends them to check the wrong thing.
 */

function setOnline(value: boolean): void {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    get: () => value,
  });
}

beforeEach(() => {
  setOnline(true);
});

afterEach(() => {
  setOnline(true);
  vi.restoreAllMocks();
});

describe("OfflineBanner", () => {
  it("renders nothing at all while online", () => {
    const { container } = render(<OfflineBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says so immediately when the page loads offline", () => {
    // A page served from the service worker cache while offline gets no
    // `offline` event: it was already offline when it started.
    setOnline(false);
    render(<OfflineBanner />);
    expect(screen.getByText(/No connection/)).toBeVisible();
  });

  it("appears when the connection drops", () => {
    render(<OfflineBanner />);
    setOnline(false);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByText(/No connection/)).toBeVisible();
  });

  it("disappears when the connection returns", () => {
    setOnline(false);
    render(<OfflineBanner />);
    setOnline(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByText(/No connection/)).toBeNull();
  });

  it("names what still works, because most of the site does", () => {
    // Everything but the live team lookup is in the bundle. A banner that says
    // only "you are offline" implies the site is unusable, which is false.
    setOnline(false);
    render(<OfflineBanner />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent(/Player records/);
    expect(banner).toHaveTextContent(/opening squad/);
    expect(banner).toHaveTextContent(/method pages/);
  });

  it("is a status region, not an alert", () => {
    // A laptop lid closing and reopening would interrupt a screen reader
    // repeatedly for no gain. Losing a connection is worth announcing; it is
    // not an error that interrupts what someone was doing.
    setOnline(false);
    render(<OfflineBanner />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveAttribute("aria-live", "polite");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("hides the icon from assistive technology", () => {
    setOnline(false);
    const { container } = render(<OfflineBanner />);
    const icon = container.querySelector("svg");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("stops listening once removed", () => {
    // A listener left behind holds the component alive and calls setState on
    // an unmounted tree every time the network flaps.
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<OfflineBanner />);
    unmount();
    const removed = remove.mock.calls.map(([event]) => event);
    expect(removed).toContain("online");
    expect(removed).toContain("offline");
  });
});
