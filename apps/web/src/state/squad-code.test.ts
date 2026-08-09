import { describe, expect, it } from "vitest";

import { decodeSquad, encodeSquad } from "./squad-code";

/**
 * A code that decodes into the wrong squad is worse than one that fails: fifteen
 * plausible names is exactly what a wrong answer looks like.
 */

const SQUAD = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 700];

describe("encodeSquad", () => {
  it("round-trips a squad through the address bar", () => {
    const code = encodeSquad(SQUAD);

    expect(code).not.toBeNull();
    expect(decodeSquad(code!)).toEqual(SQUAD);
  });

  it("stays short enough to live in a URL somebody might read", () => {
    expect(encodeSquad(SQUAD)!.length).toBeLessThan(60);
  });

  it("uses only characters a URL carries unescaped", () => {
    expect(encodeSquad(SQUAD)!).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("refuses a squad that is not fifteen players", () => {
    expect(encodeSquad(SQUAD.slice(0, 14))).toBeNull();
    expect(encodeSquad([...SQUAD, 800])).toBeNull();
  });

  it("refuses an id FPL could never have issued", () => {
    expect(encodeSquad([...SQUAD.slice(0, 14), 0])).toBeNull();
    expect(encodeSquad([...SQUAD.slice(0, 14), -3])).toBeNull();
    expect(encodeSquad([...SQUAD.slice(0, 14), 70_000])).toBeNull();
  });
});

describe("decodeSquad", () => {
  it("refuses a truncated code rather than returning a short squad", () => {
    const code = encodeSquad(SQUAD)!;

    expect(decodeSquad(code.slice(0, -4))).toBeNull();
  });

  it("refuses a code with a character changed", () => {
    const code = encodeSquad(SQUAD)!;
    const swapped = code[0] === "A" ? "B" : "A";

    expect(decodeSquad(swapped + code.slice(1))).toBeNull();
  });

  it("refuses anything that is not this code at all", () => {
    expect(decodeSquad("")).toBeNull();
    expect(decodeSquad("not a code")).toBeNull();
    expect(decodeSquad("!!!!")).toBeNull();
  });

  it("refuses a squad that names the same player twice", () => {
    const doubled = [...SQUAD.slice(0, 14), SQUAD[0]!];
    // Built by hand, because the encoder is happy to pack a repeat: the
    // duplicate is a squad rule, and this is the layer that reads a stranger's
    // link.
    const code = encodeSquad(doubled)!;

    expect(decodeSquad(code)).toBeNull();
  });
});
