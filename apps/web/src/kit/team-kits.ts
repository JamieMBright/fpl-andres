import type { KitPaint } from "../components/CeefaxShirt";
import type { TeletextColor } from "./teletext";

/**
 * Kit colours for the twenty 2026/27 Premier League clubs.
 *
 * Hardcoded because there is nowhere to fetch it from. The FPL bootstrap
 * `teams` objects carry `code`, `name`, `short_name`, strength ratings and
 * league position — and no colour of any kind. Verified against the live
 * endpoint rather than assumed.
 *
 * Keyed by FPL club `code`, not by `id`. Ids are reassigned when clubs are
 * promoted and relegated; the code follows the club.
 *
 * ## Written in palette colours, not in hex
 *
 * An earlier version stored real hex and snapped it to the palette by nearest
 * RGB distance. That distance is dominated by lightness, so it discarded the
 * hue that identifies a kit: Villa's claret landed on black and its sky-blue
 * sleeves on white, which is a Newcastle shirt. Snapping on hue instead fixed
 * claret and broke City, whose sky blue became ordinary blue.
 *
 * No automatic rule is right for every kit, so each is written directly in the
 * eight colours a Mode 7 page had. That is also the only way to say the things
 * that make a kit recognisable — which row of the collar is yellow, which way
 * the sash runs, how wide the stripes are — none of which survives a colour
 * conversion.
 *
 * ## What eight colours cost
 *
 * All twenty are distinguishable. On body colour alone they collapse to six,
 * red seven times over; it is the collars, cuffs, shoulder lines and stripe
 * arrangements that separate them. The shirt is still never the only
 * identifier: every rendered shirt carries the club in its accessible name and
 * the short name is printed beside it.
 */

export interface TeamKit {
  /** FPL club code, stable across seasons. */
  code: number;
  shortName: string;
  name: string;
  paint: KitPaint;
}

const solid = (
  base: TeletextColor,
  collar: readonly TeletextColor[],
  extra: Partial<KitPaint> = {},
): KitPaint => ({ base, sleeves: base, collar, ...extra });

export const TEAM_KITS: readonly TeamKit[] = [
  {
    code: 3,
    shortName: "ARS",
    name: "Arsenal",
    // White sleeves and shoulder, and a collar dithered from the club colours.
    paint: {
      base: "red",
      sleeves: "white",
      collar: ["red"],
      collarDither: ["black", "red"],
      shoulder: ["white"],
    },
  },
  {
    code: 7,
    shortName: "AVL",
    name: "Aston Villa",
    // Claret was magenta on Ceefax; sky blue reads as cyan.
    paint: { base: "magenta", sleeves: "cyan", collar: ["cyan"] },
  },
  {
    code: 91,
    shortName: "BOU",
    name: "Bournemouth",
    paint: solid("red", ["black"], {
      stripes: ["red", "red", "black", "black"],
      shoulder: ["yellow"],
    }),
  },
  {
    code: 94,
    shortName: "BRE",
    name: "Brentford",
    paint: solid("red", ["yellow", "black"], {
      stripes: ["red", "red", "white", "white"],
      cuffs: ["yellow", "black"],
    }),
  },
  {
    code: 36,
    shortName: "BHA",
    name: "Brighton",
    // The white stripes are much thinner than the blue.
    paint: solid("blue", ["white", "blue"], {
      stripes: ["blue", "blue", "white"],
    }),
  },
  {
    code: 8,
    shortName: "CHE",
    name: "Chelsea",
    paint: solid("blue", ["blue"]),
  },
  {
    code: 9,
    shortName: "COV",
    name: "Coventry City",
    paint: solid("cyan", ["black"], {
      stripes: ["cyan", "cyan", "white"],
    }),
  },
  {
    code: 31,
    shortName: "CRY",
    name: "Crystal Palace",
    // White base, a red-over-blue sash from top right, and a blue-over-red
    // line across the shoulders.
    paint: solid("white", ["white"], {
      shoulder: ["blue", "red"],
      sash: ["red", "blue"],
    }),
  },
  {
    code: 11,
    shortName: "EVE",
    name: "Everton",
    paint: solid("blue", ["yellow", "blue"]),
  },
  {
    code: 54,
    shortName: "FUL",
    name: "Fulham",
    paint: solid("white", ["red", "black"]),
  },
  {
    code: 88,
    shortName: "HUL",
    name: "Hull City",
    // Three bars: a four-cell black centre, amber either side, and two-cell
    // black edges.
    paint: solid("yellow", ["black"], {
      stripes: [
        "black",
        "black",
        "yellow",
        "yellow",
        "black",
        "black",
        "black",
        "black",
        "yellow",
        "yellow",
        "black",
        "black",
      ],
    }),
  },
  {
    code: 40,
    shortName: "IPS",
    name: "Ipswich Town",
    paint: solid("blue", ["white", "blue"], { cuffs: ["black"] }),
  },
  {
    code: 2,
    shortName: "LEE",
    name: "Leeds",
    paint: solid("white", ["blue"], {
      hoops: ["white", "white", "blue", "white", "white", "yellow"],
    }),
  },
  {
    code: 14,
    shortName: "LIV",
    name: "Liverpool",
    paint: solid("red", ["white", "red"]),
  },
  {
    code: 43,
    shortName: "MCI",
    name: "Manchester City",
    // White at the hem thinning into sky blue: a solid row, then four parts
    // white to one blue, then three, two, one, a half, and blue from there.
    paint: solid("cyan", ["white"], {
      fade: {
        from: "white",
        to: "cyan",
        ladder: [0, 1 / 5, 1 / 4, 1 / 3, 1 / 2, 2 / 3, 1],
      },
    }),
  },
  {
    code: 1,
    shortName: "MUN",
    name: "Manchester United",
    // Even widths, because the collar is six cells wide: three would sit a
    // half-cell off centre. Four then two narrows into a folded-over V.
    paint: solid("red", ["black", "white"], {
      cuffs: ["white"],
      collarNotch: { colour: "red", widths: [4, 2] },
    }),
  },
  {
    code: 4,
    shortName: "NEW",
    name: "Newcastle",
    // A barcode: thick black at both edges and the centre, thin between.
    paint: solid("black", ["white"], {
      stripes: [
        "black",
        "black",
        "white",
        "black",
        "white",
        "black",
        "black",
        "white",
        "black",
        "white",
        "black",
        "black",
      ],
    }),
  },
  {
    code: 17,
    shortName: "NFO",
    name: "Nottingham Forest",
    paint: solid("red", ["red"], { shoulder: ["white"] }),
  },
  {
    code: 56,
    shortName: "SUN",
    name: "Sunderland",
    paint: solid("red", ["white", "red"], {
      stripes: ["red", "red", "white", "white"],
    }),
  },
  {
    code: 6,
    shortName: "TOT",
    name: "Tottenham",
    paint: solid("white", ["white"], { sideLine: "black" }),
  },
];

const BY_CODE = new Map(TEAM_KITS.map((kit) => [kit.code, kit]));
const BY_SHORT_NAME = new Map(TEAM_KITS.map((kit) => [kit.shortName, kit]));

export function kitForCode(code: number | null | undefined): TeamKit | null {
  return code == null ? null : (BY_CODE.get(code) ?? null);
}

/**
 * Fallback lookup for the artifacts that carry a short name but no club code.
 * Prefer `kitForCode`: short names change, codes do not.
 */
export function kitForShortName(
  shortName: string | null | undefined,
): TeamKit | null {
  return shortName == null ? null : (BY_SHORT_NAME.get(shortName) ?? null);
}

export function resolveKit(kit: TeamKit): KitPaint {
  return kit.paint;
}

/** Everything that distinguishes one rendered shirt from another. */
export function signatureKey(kit: TeamKit): string {
  const { paint } = kit;
  return JSON.stringify([
    paint.base,
    paint.sleeves,
    paint.collar,
    paint.collarDither ?? null,
    paint.stripes ?? null,
    paint.hoops ?? null,
    paint.sash ?? null,
    paint.shoulder ?? null,
    paint.cuffs ?? null,
    paint.sideLine ?? null,
    paint.fade ?? null,
  ]);
}
