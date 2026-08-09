import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { InfoMarker } from "./InfoMarker";

describe("InfoMarker", () => {
  function pip(): HTMLElement {
    return screen.getByRole("button", { name: "About xPts" });
  }

  it("says nothing until asked", () => {
    render(
      <InfoMarker label="xPts">Points from every scoring route.</InfoMarker>,
    );

    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(pip()).not.toHaveAttribute("aria-describedby");
  });

  it("opens under a mouse and describes the pip while it is open", async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <InfoMarker label="xPts">Points from every scoring route.</InfoMarker>,
    );

    await user.hover(pip());

    const bubble = screen.getByRole("tooltip");
    expect(bubble).toHaveTextContent("Points from every scoring route.");
    // The pip is the thing a screen reader lands on, so the description hangs off it.
    expect(pip()).toHaveAttribute("aria-describedby", bubble.id);

    await user.unhover(pip());
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("holds open for a held finger and closes when it lifts", async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <InfoMarker label="xPts">Points from every scoring route.</InfoMarker>,
    );

    await user.pointer({ keys: "[TouchA>]", target: pip() });
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    await user.pointer({ keys: "[/TouchA]", target: pip() });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("opens on focus and Escape closes it without moving focus", async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <InfoMarker label="xPts">Points from every scoring route.</InfoMarker>,
    );

    await user.tab();
    expect(pip()).toHaveFocus();
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(pip()).toHaveFocus();
  });
});
