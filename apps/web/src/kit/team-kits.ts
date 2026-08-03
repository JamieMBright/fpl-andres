import type { TeletextColor } from "./teletext";
import { nearestTeletextColor } from "./teletext";

/**
 * Kit colours for the twenty 2026/27 Premier League clubs.
 *
 * Hardcoded because there is nowhere to fetch it from. The FPL bootstrap
 * `teams` objects carry `code`, `name`, `short_name`, strength ratings and
 * league position — and no colour of any kind. Verified against the live
 * endpoint rather than assumed.
 *
 * Keyed by FPL club `code`, not by `id`. Ids are reassigned when clubs are
 * promoted and relegated; the code follows the club. This is the same rule the
 * rest of the repository follows for players.
 *
 * `pattern` is the kit's construction, not a decoration chosen to make the
 * shirts look different. Arsenal genuinely have white sleeves; Newcastle
 * genuinely have stripes.
 *
 * ## What eight colours cost
 *
 * Measured, not estimated. Snapping to the teletext palette leaves **17 of 20**
 * clubs distinguishable on (body, secondary, collar, pattern). Three pairs
 * collide:
 *
 * | Renders as              | Clubs                  |
 * | ----------------------- | ---------------------- |
 * | blue / white / solid    | Chelsea, Everton       |
 * | cyan / white / solid    | Coventry, Man City     |
 * | white / black / solid   | Fulham, Tottenham      |
 *
 * Each pair genuinely wears a near-identical kit — two royal blue, two sky
 * blue, two white-and-navy — so this is the palette reporting a real similarity
 * rather than losing information.
 *
 * Without the collar it would be 14 of 20, with Liverpool, United and Forest
 * all identical. That is why `trim` is part of the signature.
 *
 * The shirt is therefore **never the only identifier**. Every rendered shirt
 * carries the club in its accessible name, and the short name is printed beside
 * it. `team-kits.test.ts` pins the collision set, so a kit edit that makes two
 * more clubs identical fails rather than quietly shipping.
 */

export type KitPattern = "solid" | "stripes" | "halves" | "sleeves" | "sash";

export interface TeamKit {
  /** FPL club code, stable across seasons. */
  code: number;
  shortName: string;
  name: string;
  /** Shirt body. */
  primary: string;
  /** Stripes, sleeves, or the second half — whatever the pattern uses. */
  secondary: string;
  /** Collar and cuffs. */
  trim: string;
  pattern: KitPattern;
}

export const TEAM_KITS: readonly TeamKit[] = [
  {
    code: 3,
    shortName: "ARS",
    name: "Arsenal",
    primary: "#ef0107",
    secondary: "#ffffff",
    trim: "#ffffff",
    pattern: "sleeves",
  },
  {
    code: 7,
    shortName: "AVL",
    name: "Aston Villa",
    primary: "#670e36",
    secondary: "#95bfe5",
    trim: "#95bfe5",
    pattern: "sleeves",
  },
  {
    code: 91,
    shortName: "BOU",
    name: "Bournemouth",
    primary: "#da291c",
    secondary: "#000000",
    trim: "#000000",
    pattern: "stripes",
  },
  {
    code: 94,
    shortName: "BRE",
    name: "Brentford",
    primary: "#e30613",
    secondary: "#ffffff",
    trim: "#ffffff",
    pattern: "stripes",
  },
  {
    code: 36,
    shortName: "BHA",
    name: "Brighton",
    primary: "#0057b8",
    secondary: "#ffffff",
    trim: "#ffffff",
    pattern: "stripes",
  },
  {
    code: 8,
    shortName: "CHE",
    name: "Chelsea",
    primary: "#034694",
    secondary: "#ffffff",
    trim: "#ffffff",
    pattern: "solid",
  },
  {
    code: 9,
    shortName: "COV",
    name: "Coventry City",
    primary: "#78d0f3",
    secondary: "#ffffff",
    trim: "#1d1d1b",
    pattern: "solid",
  },
  {
    code: 31,
    shortName: "CRY",
    name: "Crystal Palace",
    primary: "#1b458f",
    secondary: "#c4122e",
    trim: "#ffffff",
    pattern: "stripes",
  },
  {
    code: 11,
    shortName: "EVE",
    name: "Everton",
    primary: "#003399",
    secondary: "#ffffff",
    trim: "#ffffff",
    pattern: "solid",
  },
  {
    code: 54,
    shortName: "FUL",
    name: "Fulham",
    primary: "#ffffff",
    secondary: "#000000",
    trim: "#000000",
    pattern: "solid",
  },
  {
    code: 88,
    shortName: "HUL",
    name: "Hull City",
    primary: "#f5a12d",
    secondary: "#000000",
    trim: "#000000",
    pattern: "stripes",
  },
  {
    code: 40,
    shortName: "IPS",
    name: "Ipswich Town",
    primary: "#0044a9",
    secondary: "#ffffff",
    trim: "#ffffff",
    pattern: "sleeves",
  },
  {
    code: 2,
    shortName: "LEE",
    name: "Leeds",
    primary: "#ffffff",
    secondary: "#1d428a",
    trim: "#ffe100",
    pattern: "solid",
  },
  {
    code: 14,
    shortName: "LIV",
    name: "Liverpool",
    primary: "#c8102e",
    secondary: "#c8102e",
    trim: "#ffffff",
    pattern: "solid",
  },
  {
    code: 43,
    shortName: "MCI",
    name: "Manchester City",
    primary: "#6cabdd",
    secondary: "#ffffff",
    trim: "#1c2c5b",
    pattern: "solid",
  },
  {
    code: 1,
    shortName: "MUN",
    name: "Manchester United",
    primary: "#da291c",
    secondary: "#da291c",
    trim: "#000000",
    pattern: "solid",
  },
  {
    code: 4,
    shortName: "NEW",
    name: "Newcastle",
    primary: "#241f20",
    secondary: "#ffffff",
    trim: "#ffffff",
    pattern: "stripes",
  },
  {
    code: 17,
    shortName: "NFO",
    name: "Nottingham Forest",
    primary: "#dd0000",
    secondary: "#dd0000",
    trim: "#dd0000",
    pattern: "solid",
  },
  {
    code: 56,
    shortName: "SUN",
    name: "Sunderland",
    primary: "#eb172b",
    secondary: "#ffffff",
    trim: "#000000",
    pattern: "stripes",
  },
  {
    code: 6,
    shortName: "TOT",
    name: "Tottenham",
    primary: "#ffffff",
    secondary: "#132257",
    trim: "#132257",
    pattern: "solid",
  },
];

const BY_CODE = new Map(TEAM_KITS.map((kit) => [kit.code, kit]));
const BY_SHORT_NAME = new Map(TEAM_KITS.map((kit) => [kit.shortName, kit]));

export function kitForCode(code: number | null | undefined): TeamKit | null {
  return code == null ? null : (BY_CODE.get(code) ?? null);
}

/**
 * Fallback lookup for the artifacts that carry a short name but no club code.
 * Prefer `kitForCode`: short names change (Nottingham Forest has been NFO and
 * NOT), codes do not.
 */
export function kitForShortName(
  shortName: string | null | undefined,
): TeamKit | null {
  return shortName == null ? null : (BY_SHORT_NAME.get(shortName) ?? null);
}

/** What the renderer will actually draw, after the palette has had its way. */
export interface KitSignature {
  primary: TeletextColor;
  secondary: TeletextColor;
  /**
   * The collar. Included because it is what separates the three red clubs:
   * Liverpool white, United black, Forest red. Without it they render
   * identically, and a collar is something teletext shirts genuinely had.
   */
  trim: TeletextColor;
  pattern: KitPattern;
}

export function kitSignature(kit: TeamKit): KitSignature {
  return {
    primary: nearestTeletextColor(kit.primary),
    secondary: nearestTeletextColor(kit.secondary),
    trim: nearestTeletextColor(kit.trim),
    pattern: kit.pattern,
  };
}

export function signatureKey(signature: KitSignature): string {
  return `${signature.primary}/${signature.secondary}/${signature.trim}/${signature.pattern}`;
}
