import { describe, expect, it } from "vitest";

import {
  inkOn,
  nearestTeletextColor,
  parseHex,
  snapToTeletext,
  TELETEXT_PALETTE,
} from "./teletext";

describe("parseHex", () => {
  it("accepts the forms a stylesheet would produce", () => {
    expect(parseHex("#ff0000")).toEqual([255, 0, 0]);
    expect(parseHex("ff0000")).toEqual([255, 0, 0]);
    expect(parseHex("#f00")).toEqual([255, 0, 0]);
    expect(parseHex("#FF0000")).toEqual([255, 0, 0]);
  });

  it("returns null rather than a default for anything else", () => {
    expect(parseHex("")).toBeNull();
    expect(parseHex("#ff00")).toBeNull();
    expect(parseHex("red")).toBeNull();
    expect(parseHex("#gggggg")).toBeNull();
  });
});

describe("nearestTeletextColor", () => {
  it("maps each palette entry to itself", () => {
    for (const [name, hex] of Object.entries(TELETEXT_PALETTE)) {
      expect(nearestTeletextColor(hex)).toBe(name);
    }
  });

  it("snaps real club colours the way a 1974 decoder would", () => {
    expect(nearestTeletextColor("#ef0107")).toBe("red"); // Arsenal
    expect(nearestTeletextColor("#6cabdd")).toBe("cyan"); // Man City sky blue
    expect(nearestTeletextColor("#fdb913")).toBe("yellow"); // Wolves gold
    expect(nearestTeletextColor("#241f20")).toBe("black"); // Newcastle
    expect(nearestTeletextColor("#034694")).toBe("blue"); // Chelsea
  });

  it("throws on unparseable input instead of guessing a colour", () => {
    expect(() => nearestTeletextColor("not a colour")).toThrow(/not a colour/);
  });

  it("is deterministic when two palette entries are equidistant", () => {
    // Mid grey is the same distance from black and white.
    const first = nearestTeletextColor("#808080");
    for (let i = 0; i < 5; i += 1) {
      expect(nearestTeletextColor("#808080")).toBe(first);
    }
  });
});

describe("snapToTeletext", () => {
  it("returns a palette hex, not the input", () => {
    expect(snapToTeletext("#ef0107")).toBe("#ff0000");
  });
});

describe("inkOn", () => {
  it("puts light ink on the dark half of the palette and dark ink on the light half", () => {
    expect(inkOn("black")).toBe("#ffffff");
    expect(inkOn("blue")).toBe("#ffffff");
    expect(inkOn("red")).toBe("#ffffff");
    expect(inkOn("magenta")).toBe("#ffffff");

    expect(inkOn("white")).toBe("#000000");
    expect(inkOn("yellow")).toBe("#000000");
    expect(inkOn("cyan")).toBe("#000000");
    expect(inkOn("green")).toBe("#000000");
  });

  it("covers every palette entry", () => {
    for (const name of Object.keys(TELETEXT_PALETTE)) {
      expect(() => inkOn(name as keyof typeof TELETEXT_PALETTE)).not.toThrow();
    }
  });
});
