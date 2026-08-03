import { TELETEXT_PALETTE, type TeletextColor } from "./teletext";
import { TEAM_KITS } from "./team-kits";

/**
 * A marker per club, taken from the shirt it wears.
 *
 * Twenty clubs against eight teletext colours collide heavily — seven of them
 * play in red. So the mark carries three things from the kit rather than one:
 * the base colour fills it, the first accent that differs from the base outlines
 * it, and where two clubs still land on the same pair the outline is dashed to
 * separate them.
 *
 * The mark is never the only identifier. Position is already carried by the
 * shape, the club is named in the hover label, and the legend lists every
 * swatch. This is a way of grouping a scatter by eye, not a way of reading a
 * club off a single dot.
 */

export interface ClubMarker {
  shortName: string;
  name: string;
  fill: string;
  stroke: string;
  /** An SVG `stroke-dasharray`, or null for a solid outline. */
  dash: string | null;
}

// Enough to separate the largest collision group. If a kit change makes a group
// bigger than this, the uniqueness test beside this file fails rather than two
// clubs silently sharing a mark.
const DASHES: (string | null)[] = [null, "5 2.5", "2 2", "1 1.75", "7 2 1 2"];

function accentOf(kit: (typeof TEAM_KITS)[number]): TeletextColor {
  const { base, sleeves, collar, stripes, hoops, sash, shoulder, cuffs } =
    kit.paint;
  const candidates: readonly (TeletextColor | undefined)[] = [
    sleeves,
    ...collar,
    ...(stripes ?? []),
    ...(hoops ?? []),
    ...(sash ?? []),
    ...(shoulder ?? []),
    ...(cuffs ?? []),
  ];
  return candidates.find((colour) => colour && colour !== base) ?? base;
}

function build(): Map<string, ClubMarker> {
  const groups = new Map<string, number>();
  const markers = new Map<string, ClubMarker>();

  for (const kit of TEAM_KITS) {
    const accent = accentOf(kit);
    const key = `${kit.paint.base}/${accent}`;
    const seen = groups.get(key) ?? 0;
    groups.set(key, seen + 1);
    markers.set(kit.shortName, {
      shortName: kit.shortName,
      name: kit.name,
      fill: TELETEXT_PALETTE[kit.paint.base],
      stroke: TELETEXT_PALETTE[accent],
      dash: DASHES[seen % DASHES.length] ?? null,
    });
  }
  return markers;
}

const MARKERS = build();

export function clubMarker(
  shortName: string | null | undefined,
): ClubMarker | null {
  return shortName ? (MARKERS.get(shortName) ?? null) : null;
}

/** Every club's mark, in the order the kits are declared. */
export function clubMarkers(): ClubMarker[] {
  return [...MARKERS.values()];
}
