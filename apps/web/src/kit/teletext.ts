/**
 * The eight colours a Mode 7 teletext page could display.
 *
 * Not a stylistic approximation: these are the full-intensity RGB combinations
 * the SAA5050 character generator could produce, which is why there are exactly
 * eight and why none of them is a mid-tone. Everything drawn from this palette
 * inherits the constraint that made Ceefax look the way it did.
 *
 * The cost is real and worth stating up front: twenty clubs snapped to eight
 * colours collide heavily. `team-kits.ts` records exactly which, and why the
 * shirt is never the only thing identifying a player.
 */

export const TELETEXT_PALETTE = {
  black: "#000000",
  red: "#ff0000",
  green: "#00ff00",
  yellow: "#ffff00",
  blue: "#0000ff",
  magenta: "#ff00ff",
  cyan: "#00ffff",
  white: "#ffffff",
} as const;

export type TeletextColor = keyof typeof TELETEXT_PALETTE;

const RGB: Record<TeletextColor, readonly [number, number, number]> = {
  black: [0, 0, 0],
  red: [255, 0, 0],
  green: [0, 255, 0],
  yellow: [255, 255, 0],
  blue: [0, 0, 255],
  magenta: [255, 0, 255],
  cyan: [0, 255, 255],
  white: [255, 255, 255],
};

const NAMES = Object.keys(RGB) as TeletextColor[];

const SHORT_HEX = /^#?([0-9a-f])([0-9a-f])([0-9a-f])$/i;
const LONG_HEX = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i;

/**
 * Parses `#rgb`, `#rrggbb`, and the same without the hash.
 *
 * Returns null rather than throwing or defaulting. A club colour that cannot be
 * read is a data error the caller should surface, and quietly rendering black
 * would put a plausible-looking wrong shirt on the pitch.
 */
export function parseHex(value: string): [number, number, number] | null {
  const short = SHORT_HEX.exec(value.trim());
  if (short) {
    return [
      Number.parseInt(short[1]! + short[1]!, 16),
      Number.parseInt(short[2]! + short[2]!, 16),
      Number.parseInt(short[3]! + short[3]!, 16),
    ];
  }
  const long = LONG_HEX.exec(value.trim());
  if (!long) return null;
  return [
    Number.parseInt(long[1]!, 16),
    Number.parseInt(long[2]!, 16),
    Number.parseInt(long[3]!, 16),
  ];
}

/**
 * The nearest teletext colour by Euclidean distance in RGB.
 *
 * RGB distance is not how eyes work — it overweights green and treats a dark
 * navy as closer to black than a human would. A perceptual space like CIELAB
 * would be more faithful to what people see.
 *
 * Kept anyway, because faithfulness to human vision is the wrong target here.
 * The point is to look like a machine from 1974 quantising a photograph, and
 * that machine was doing exactly this arithmetic.
 *
 * Ties break toward the earlier palette entry, which makes the function total
 * and deterministic; without it, a colour equidistant from two palette entries
 * could render differently between runs.
 */
export function nearestTeletextColor(hex: string): TeletextColor {
  const rgb = parseHex(hex);
  if (!rgb) {
    throw new Error(`${hex} is not a hex colour`);
  }
  let best: TeletextColor = "black";
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const name of NAMES) {
    const [r, g, b] = RGB[name];
    const distance = (rgb[0] - r) ** 2 + (rgb[1] - g) ** 2 + (rgb[2] - b) ** 2;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = name;
    }
  }
  return best;
}

/** The snapped colour as a hex string, for direct use as an SVG fill. */
export function snapToTeletext(hex: string): string {
  return TELETEXT_PALETTE[nearestTeletextColor(hex)];
}

/**
 * Whether text on this colour should be black.
 *
 * Only eight cases, so this is a lookup rather than a contrast calculation:
 * the four bright colours take black text, the four dark ones take white. That
 * matches what teletext actually did and avoids pretending a computed ratio is
 * meaningful across a palette this small.
 */
export function inkOn(background: TeletextColor): string {
  const dark: TeletextColor[] = ["black", "red", "blue", "magenta"];
  return dark.includes(background)
    ? TELETEXT_PALETTE.white
    : TELETEXT_PALETTE.black;
}
