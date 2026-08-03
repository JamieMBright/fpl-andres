import { memo } from "react";

import type { TeamKit } from "../kit/team-kits";
import { resolveKit } from "../kit/team-kits";
import { inkOn, TELETEXT_PALETTE, type TeletextColor } from "../kit/teletext";

/**
 * A club shirt drawn as a teletext block graphic.
 *
 * Built by painting a coarse grid of cells in layers, not by composing
 * rectangles. Real kits carry details a fixed pattern list cannot express — a
 * diagonal sash over a shoulder line over a base, a cuff one cell wide, a
 * collar of three differently coloured rows — and each of those is one more
 * pass over the same grid rather than one more shape to position.
 *
 * The grid stays coarse on purpose. Sixteen by sixteen is close to what a Mode
 * 7 page had to work with, and it forces a stripe to land on whole cells rather
 * than being a thin rectangle that happens to look blocky.
 */

const COLS = 16;
const ROWS = 14;
const CELL = 4;

const BODY_X = 2;
const BODY_W = 12;
const BODY_Y = 2;
const BODY_H = ROWS - BODY_Y;

const SLEEVE_W = 2;
const SLEEVE_H = 5;

// Two rows, six wide. Three rows of four read as a chimney on a twelve-wide
// body rather than as a collar.
const COLLAR_X = 5;
const COLLAR_W = 6;
const COLLAR_H = 2;

/**
 * Which columns of a row take the second colour, spread as evenly as the row
 * allows and shifted per row so they do not stack into vertical lines.
 *
 * Five is coprime with the twelve-cell body, so successive rows land on
 * different columns rather than repeating every other row.
 */
function scatter(count: number, width: number, row: number): Set<number> {
  const chosen = new Set<number>();
  if (count <= 0) return chosen;
  if (count >= width) {
    for (let column = 0; column < width; column += 1) chosen.add(column);
    return chosen;
  }
  for (let index = 0; index < count; index += 1) {
    const spaced = Math.floor(((index + 0.5) * width) / count);
    chosen.add((spaced + row * 5) % width);
  }
  return chosen;
}

type Grid = (TeletextColor | null)[][];

export interface KitPaint {
  base: TeletextColor;
  sleeves: TeletextColor;
  collar: readonly TeletextColor[];
  collarDither?: readonly [TeletextColor, TeletextColor];
  /** Per body column, cycled. Twelve columns of body to fill. */
  stripes?: readonly TeletextColor[];
  /** Per body row, cycled. */
  hoops?: readonly TeletextColor[];
  /** Diagonal band, top right to bottom left, in the order given. */
  sash?: readonly TeletextColor[];
  /** Horizontal lines across the top of the body, first is highest. */
  shoulder?: readonly TeletextColor[];
  /** Sleeve cuffs, outermost column first. */
  cuffs?: readonly TeletextColor[];
  /** One cell wide down both seams, below the sleeve to four fifths down. */
  sideLine?: TeletextColor;
  /**
   * A fade up the body. `ladder` is the share of each row taking `to`, counted
   * from the hem up; rows above the ladder are solid `to`.
   */
  fade?: { from: TeletextColor; to: TeletextColor; ladder: readonly number[] };
  /** A notch cut into the collar, one width per row, to suggest a fold. */
  collarNotch?: { colour: TeletextColor; widths: readonly number[] };
}

function paint(
  grid: Grid,
  x: number,
  y: number,
  width: number,
  height: number,
  colour: TeletextColor,
): void {
  for (let row = y; row < y + height && row < ROWS; row += 1) {
    for (let column = x; column < x + width && column < COLS; column += 1) {
      if (row >= 0 && column >= 0) grid[row]![column] = colour;
    }
  }
}

function buildGrid(spec: KitPaint): Grid {
  const grid: Grid = Array.from({ length: ROWS }, () =>
    Array<TeletextColor | null>(COLS).fill(null),
  );

  paint(grid, BODY_X, BODY_Y, BODY_W, BODY_H, spec.base);
  paint(grid, 0, BODY_Y, SLEEVE_W, SLEEVE_H, spec.sleeves);
  paint(grid, COLS - SLEEVE_W, BODY_Y, SLEEVE_W, SLEEVE_H, spec.sleeves);

  if (spec.stripes) {
    const pattern = spec.stripes;
    for (let column = 0; column < BODY_W; column += 1) {
      const colour = pattern[column % pattern.length];
      if (colour) paint(grid, BODY_X + column, BODY_Y, 1, BODY_H, colour);
    }
  }

  if (spec.hoops) {
    const pattern = spec.hoops;
    for (let row = 0; row < BODY_H; row += 1) {
      const colour = pattern[row % pattern.length];
      if (colour) paint(grid, BODY_X, BODY_Y + row, BODY_W, 1, colour);
    }
  }

  if (spec.fade) {
    const { from, to, ladder } = spec.fade;
    for (let row = 0; row < BODY_H; row += 1) {
      const fromHem = BODY_H - 1 - row;
      const share = ladder[fromHem] ?? 1;
      const chosen = scatter(Math.round(share * BODY_W), BODY_W, fromHem);
      for (let column = 0; column < BODY_W; column += 1) {
        paint(
          grid,
          BODY_X + column,
          BODY_Y + row,
          1,
          1,
          chosen.has(column) ? to : from,
        );
      }
    }
  }

  if (spec.sash) {
    const colours = spec.sash;
    for (let row = 0; row < BODY_H; row += 1) {
      const lead =
        BODY_X +
        BODY_W -
        1 -
        Math.floor((row / Math.max(1, BODY_H - 1)) * (BODY_W - 1));
      colours.forEach((colour, offset) => {
        const column = lead + offset;
        if (column >= BODY_X && column < BODY_X + BODY_W) {
          paint(grid, column, BODY_Y + row, 1, 1, colour);
        }
      });
    }
  }

  spec.shoulder?.forEach((colour, row) => {
    paint(grid, BODY_X, BODY_Y + row, BODY_W, 1, colour);
  });

  if (spec.sideLine) {
    // Below the sleeve, not beside it: starting at the shoulder draws a line
    // between sleeve and torso instead of down the side seam.
    const top = BODY_Y + SLEEVE_H;
    const bottom = BODY_Y + Math.round(BODY_H * 0.8);
    paint(grid, BODY_X, top, 1, bottom - top, spec.sideLine);
    paint(grid, BODY_X + BODY_W - 1, top, 1, bottom - top, spec.sideLine);
  }

  spec.cuffs?.forEach((colour, depth) => {
    paint(grid, depth, BODY_Y, 1, SLEEVE_H, colour);
    paint(grid, COLS - 1 - depth, BODY_Y, 1, SLEEVE_H, colour);
  });

  if (spec.collarDither) {
    const [first, second] = spec.collarDither;
    for (let row = 0; row < COLLAR_H; row += 1) {
      for (let column = 0; column < COLLAR_W; column += 1) {
        paint(
          grid,
          COLLAR_X + column,
          row,
          1,
          1,
          (row + column) % 2 === 0 ? first : second,
        );
      }
    }
  } else {
    for (let row = 0; row < COLLAR_H; row += 1) {
      const colour = spec.collar[Math.min(row, spec.collar.length - 1)];
      if (colour) paint(grid, COLLAR_X, row, COLLAR_W, 1, colour);
    }
  }

  // Drawn last so it cuts through whatever the collar laid down.
  spec.collarNotch?.widths.forEach((width, row) => {
    if (width <= 0 || row >= COLLAR_H) return;
    const start = COLLAR_X + Math.floor((COLLAR_W - width) / 2);
    paint(grid, start, row, width, 1, spec.collarNotch!.colour);
  });

  return grid;
}

interface Run {
  x: number;
  y: number;
  width: number;
  colour: TeletextColor;
}

/** Merge horizontal neighbours: 256 cells becomes a few dozen rectangles. */
function runs(grid: Grid): Run[] {
  const merged: Run[] = [];
  for (let row = 0; row < ROWS; row += 1) {
    let start = -1;
    let colour: TeletextColor | null = null;
    for (let column = 0; column <= COLS; column += 1) {
      const here = column < COLS ? grid[row]![column]! : null;
      if (here !== colour) {
        if (colour !== null && start >= 0) {
          merged.push({ x: start, y: row, width: column - start, colour });
        }
        colour = here;
        start = column;
      }
    }
  }
  return merged;
}

export interface CeefaxShirtProps {
  kit: TeamKit;
  /** Squad number, printed across the chest. Omit for a blank shirt. */
  squadNumber?: number | null;
  /**
   * Overrides the accessible name. Pass null when an adjacent element already
   * names the club, so a screen reader does not hear it twice.
   */
  label?: string | null;
  className?: string;
}

function CeefaxShirtImpl({
  kit,
  squadNumber = null,
  label,
  className,
}: CeefaxShirtProps) {
  const spec = resolveKit(kit);
  const cells = runs(buildGrid(spec));
  const accessibleName = label === null ? null : (label ?? `${kit.name} shirt`);

  return (
    <svg
      aria-hidden={accessibleName === null ? "true" : undefined}
      aria-label={accessibleName ?? undefined}
      className={className ? `ceefax-shirt ${className}` : "ceefax-shirt"}
      focusable="false"
      role={accessibleName === null ? undefined : "img"}
      viewBox={`0 0 ${COLS * CELL} ${ROWS * CELL}`}
    >
      {accessibleName === null ? null : <title>{accessibleName}</title>}

      {cells.map((run) => (
        <rect
          key={`${run.x}-${run.y}`}
          x={run.x * CELL}
          y={run.y * CELL}
          width={run.width * CELL}
          height={CELL}
          fill={TELETEXT_PALETTE[run.colour]}
        />
      ))}

      {squadNumber === null ? null : (
        <>
          {/*
           * A solid patch behind the number. Drawn straight onto the shirt the
           * digits cross a stripe boundary and Newcastle's black-on-white is
           * unreadable; the patch fixes contrast by construction rather than by
           * which stripe the digit happened to land on.
           */}
          <rect
            x={(BODY_X + 3) * CELL}
            y={(BODY_Y + 4) * CELL}
            width={(BODY_W - 6) * CELL}
            height={4 * CELL}
            fill={TELETEXT_PALETTE[spec.base]}
          />
          <text
            className="ceefax-shirt-number"
            x={(COLS * CELL) / 2}
            y={(BODY_Y + 7) * CELL}
            fill={inkOn(spec.base)}
            textAnchor="middle"
          >
            {squadNumber}
          </text>
        </>
      )}
    </svg>
  );
}

/**
 * Fifteen shirts re-render on every pitch state change and none of them depend
 * on that state. `TeamKit` objects come from a frozen module-level array, so
 * the default shallow comparison is enough.
 */
export const CeefaxShirt = memo(CeefaxShirtImpl);
