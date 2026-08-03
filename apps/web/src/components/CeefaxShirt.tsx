import { memo } from "react";

import type { KitPattern, TeamKit } from "../kit/team-kits";
import { inkOn, nearestTeletextColor, TELETEXT_PALETTE } from "../kit/teletext";

/**
 * A club shirt drawn as a teletext block graphic.
 *
 * Built from a 12 x 14 grid because that is roughly what a Mode 7 page had to
 * work with, and because a coarse grid is what forces the stripes to land on
 * whole blocks rather than being drawn as thin rectangles that happen to look
 * blocky. Every coordinate below is a grid cell, scaled once on the way out.
 *
 * Pure and memoised: the same kit and number always produce the same SVG, and
 * a pitch renders fifteen of these on every state change.
 */

const COLS = 12;
const ROWS = 14;
const CELL = 4;

/** Body occupies the middle eight columns; sleeves take two either side. */
const BODY_X = 2;
const BODY_W = 8;
const SLEEVE_W = 2;
const SHOULDER_Y = 2;
const SLEEVE_H = 4;

interface Block {
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string;
}

function bodyBlocks(
  pattern: KitPattern,
  primary: string,
  secondary: string,
): Block[] {
  const full: Block = {
    x: BODY_X,
    y: SHOULDER_Y,
    width: BODY_W,
    height: ROWS - SHOULDER_Y,
    fill: primary,
  };

  switch (pattern) {
    case "solid":
    case "sleeves":
      return [full];

    case "stripes": {
      // Four two-column stripes. An odd count would put the same colour on both
      // edges and read as a solid shirt with a line down the middle.
      const blocks: Block[] = [];
      for (let index = 0; index < 4; index += 1) {
        blocks.push({
          x: BODY_X + index * 2,
          y: SHOULDER_Y,
          width: 2,
          height: ROWS - SHOULDER_Y,
          fill: index % 2 === 0 ? primary : secondary,
        });
      }
      return blocks;
    }

    case "hoops": {
      // Horizontal bands, one grid row each, the full length of the shirt.
      const blocks: Block[] = [];
      for (let row = 0; row < ROWS - SHOULDER_Y; row += 1) {
        blocks.push({
          x: BODY_X,
          y: SHOULDER_Y + row,
          width: BODY_W,
          height: 1,
          fill: row % 2 === 0 ? primary : secondary,
        });
      }
      return blocks;
    }

    case "halves":
      return [
        { ...full, width: BODY_W / 2 },
        { ...full, x: BODY_X + BODY_W / 2, width: BODY_W / 2, fill: secondary },
      ];

    case "sash": {
      // A diagonal in a block medium is a staircase. Drawn as one cell per row
      // so it steps rather than smooths, which is the whole point.
      const blocks: Block[] = [full];
      for (let row = 0; row < ROWS - SHOULDER_Y; row += 1) {
        const x =
          BODY_X +
          Math.min(
            BODY_W - 2,
            Math.floor((row / (ROWS - SHOULDER_Y)) * BODY_W),
          );
        blocks.push({
          x,
          y: SHOULDER_Y + row,
          width: 2,
          height: 1,
          fill: secondary,
        });
      }
      return blocks;
    }
  }
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
  const primaryName =
    kit.teletext?.primary ?? nearestTeletextColor(kit.primary);
  const secondaryName =
    kit.teletext?.secondary ?? nearestTeletextColor(kit.secondary);
  const trimName = kit.teletext?.trim ?? nearestTeletextColor(kit.trim);

  const primary = TELETEXT_PALETTE[primaryName];
  const secondary = TELETEXT_PALETTE[secondaryName];
  const trim = TELETEXT_PALETTE[trimName];
  const trimUpper =
    kit.trimUpper === undefined
      ? null
      : TELETEXT_PALETTE[nearestTeletextColor(kit.trimUpper)];

  // Contrast sleeves are a kit feature, not a pattern applied to the body.
  const sleeveFill = kit.pattern === "sleeves" ? secondary : primary;
  const blocks = bodyBlocks(kit.pattern, primary, secondary);
  const dither = kit.dither
    ? ([
        TELETEXT_PALETTE[kit.dither[0]],
        TELETEXT_PALETTE[kit.dither[1]],
      ] as const)
    : null;

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

      <rect
        x={0}
        y={SHOULDER_Y * CELL}
        width={SLEEVE_W * CELL}
        height={SLEEVE_H * CELL}
        fill={sleeveFill}
      />
      <rect
        x={(COLS - SLEEVE_W) * CELL}
        y={SHOULDER_Y * CELL}
        width={SLEEVE_W * CELL}
        height={SLEEVE_H * CELL}
        fill={sleeveFill}
      />

      {blocks.map((block) => (
        <rect
          key={`${block.x}-${block.y}-${block.fill}`}
          x={block.x * CELL}
          y={block.y * CELL}
          width={block.width * CELL}
          height={block.height * CELL}
          fill={block.fill}
        />
      ))}

      {dither === null
        ? null
        : /* Checkerboard only the body colour, so Hull's black stripes survive
             being turned amber. One cell per square, and the eye mixes two
             palette colours into a third the palette does not have. */
          blocks
            .filter((block) => block.fill === primary)
            .flatMap((block) =>
              Array.from({ length: block.height }, (_, row) =>
                Array.from({ length: block.width }, (_, column) => (
                  <rect
                    key={`dither-${block.x + column}-${block.y + row}`}
                    x={(block.x + column) * CELL}
                    y={(block.y + row) * CELL}
                    width={CELL}
                    height={CELL}
                    fill={dither[(block.y + row + block.x + column) % 2]}
                  />
                )),
              ),
            )}

      <rect
        x={(BODY_X + 2) * CELL}
        y={trimUpper === null ? 0 : CELL}
        width={(BODY_W - 4) * CELL}
        height={(trimUpper === null ? SHOULDER_Y : SHOULDER_Y - 1) * CELL}
        fill={trim}
      />
      {trimUpper === null ? null : (
        <rect
          x={(BODY_X + 2) * CELL}
          y={0}
          width={(BODY_W - 4) * CELL}
          height={CELL}
          fill={trimUpper}
        />
      )}

      {squadNumber === null ? null : (
        <>
          {/*
           * A solid patch behind the number. Without it the digits sit across a
           * stripe boundary and Newcastle's black-on-white becomes unreadable;
           * with it the contrast is fixed by construction rather than by which
           * colour the stripe happened to land on.
           */}
          <rect
            x={(BODY_X + 2) * CELL}
            y={(SHOULDER_Y + 3) * CELL}
            width={(BODY_W - 4) * CELL}
            height={4 * CELL}
            fill={primary}
          />
          <text
            className="ceefax-shirt-number"
            x={(COLS * CELL) / 2}
            y={(ROWS * CELL) / 2 + CELL}
            fill={inkOn(primaryName)}
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
