import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Countdown } from "./Countdown";

/** Fixed so the arithmetic is the subject, not the clock on the wall. */
const NOW = new Date("2026-08-20T12:00:00Z");

function at(offsetMinutes: number): string {
  return new Date(NOW.getTime() + offsetMinutes * 60_000).toISOString();
}

afterEach(() => {
  vi.useRealTimers();
});

describe("Countdown", () => {
  function renderAt(deadline: string): HTMLElement {
    cleanup();
    vi.useFakeTimers({ now: NOW });
    render(<Countdown deadline={deadline} />);
    return screen.getByText(/Next GW deadline/).parentElement!;
  }

  it("counts down to the minute", () => {
    expect(renderAt(at(3 * 1440 + 4 * 60 + 7))).toHaveTextContent("3d 4h 7m");
  });

  it("drops the days once inside one", () => {
    expect(renderAt(at(4 * 60 + 7))).toHaveTextContent("4h 7m");
    expect(renderAt(at(4 * 60 + 7))).not.toHaveTextContent("0d");
  });

  // Green, amber, red: the ramp is the point of putting a clock in the header.
  it("warms from calm to now as the deadline closes", () => {
    expect(renderAt(at(3 * 1440))).toHaveClass("is-calm");
    expect(renderAt(at(24 * 60))).toHaveClass("is-near");
    expect(renderAt(at(90))).toHaveClass("is-now");
  });

  it("does not count past the deadline", () => {
    expect(renderAt(at(-120))).toHaveTextContent("GONE");
  });
});
