import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { serialisedScatterSvg } from "./scatter-export";

describe("scatter SVG export", () => {
  it("keeps text paint order so the outline stays behind the fill", () => {
    const { container } = render(
      <svg viewBox="0 0 100 100">
        <text
          className="scatter-label"
          style={{ fill: "white", paintOrder: "stroke", stroke: "black" }}
        >
          Player
        </text>
      </svg>,
    );
    const svg = container.querySelector("svg");
    const label = container.querySelector("text");
    expect(svg).not.toBeNull();
    label?.setAttribute("style", "fill:white;stroke:black;paint-order:stroke");

    const markup = serialisedScatterSvg(svg!);

    expect(markup).toContain("paint-order:stroke");
    expect(markup).toContain("fill:white");
  });
});
