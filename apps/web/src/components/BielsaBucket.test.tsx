import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BielsaBucket } from "./BielsaBucket";
import { TELETEXT_PALETTE } from "../kit/teletext";

const PALETTE: string[] = Object.values(TELETEXT_PALETTE);

/**
 * The mark is the one place a near-miss colour is easiest to introduce and
 * hardest to notice: it is a logo, nobody diffs an SVG path, and `#00a13e`
 * reads as green to a reviewer. It was drawn in four such near-misses plus two
 * translucent details, which Mode 7 could not produce at all.
 */
describe("BielsaBucket", () => {
  function marked(): SVGElement {
    const { container } = render(<BielsaBucket />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    return svg!;
  }

  it("paints nothing that a teletext page could not", () => {
    const painted = [...marked().querySelectorAll("[fill], [stroke]")].flatMap(
      (node) =>
        ["fill", "stroke"]
          .map((attribute) => node.getAttribute(attribute))
          .filter(
            (value): value is string => value !== null && value !== "none",
          ),
    );

    expect(painted.length).toBeGreaterThan(4);
    for (const colour of painted) {
      expect(PALETTE).toContain(colour.toLowerCase());
    }
  });

  it("draws nothing part-way transparent", () => {
    // Mode 7 had no alpha. A faded shadow is a modern effect wearing the look.
    for (const node of marked().querySelectorAll("*")) {
      expect(node.getAttribute("opacity")).toBeNull();
      expect(node.getAttribute("fill-opacity")).toBeNull();
      expect(node.getAttribute("stroke-opacity")).toBeNull();
    }
  });

  it("is hidden from a screen reader, because the wordmark beside it says it", () => {
    expect(marked().getAttribute("aria-hidden")).toBe("true");
  });
});
