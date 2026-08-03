import { useState } from "react";

import {
  getPlayerPhotoUrl,
  isPhotoKnownMissing,
  markPhotoMissing,
} from "../kit/player-photo";

/**
 * A player headshot, or a silhouette when there is not one.
 *
 * Falls back on the `error` event rather than on a status code: a missing photo
 * returns 403 from the media host, not 404, and the browser does not expose the
 * status to an `<img>` anyway.
 *
 * Lazy-loaded and explicitly sized. A fifteen-player pitch is roughly 1.6 MB of
 * photographs, and without dimensions each one shifts the layout as it lands.
 */

const WIDTH = 110;
const HEIGHT = 140;

/** Ceefax-flavoured: blocky, one colour, no gradient. */
function Silhouette() {
  return (
    <svg
      aria-hidden="true"
      className="player-avatar-fallback"
      focusable="false"
      viewBox="0 0 11 14"
    >
      <rect x={4} y={2} width={3} height={3} />
      <rect x={3} y={6} width={5} height={5} />
      <rect x={2} y={8} width={1} height={3} />
      <rect x={8} y={8} width={1} height={3} />
    </svg>
  );
}

export interface PlayerAvatarProps {
  /** FPL element code. Stable across seasons, unlike the element id. */
  playerCode: number | null | undefined;
  /** The player's name, for the accessible name. */
  name: string;
  className?: string;
}

export function PlayerAvatar({
  playerCode,
  name,
  className,
}: PlayerAvatarProps) {
  const usable = typeof playerCode === "number" && playerCode > 0;
  // Remembering *which* player failed rather than *that* one did means a
  // different player in the same slot retries instead of inheriting the miss.
  const [failedFor, setFailedFor] = useState<number | null>(null);
  const failed =
    !usable || failedFor === playerCode || isPhotoKnownMissing(playerCode);

  const wrapper = className ? `player-avatar ${className}` : "player-avatar";

  if (!usable || failed) {
    return (
      <span
        className={`${wrapper} player-avatar-empty`}
        role="img"
        aria-label={`${name}, no photograph`}
      >
        <Silhouette />
      </span>
    );
  }

  return (
    <span className={wrapper}>
      <img
        alt={name}
        decoding="async"
        height={HEIGHT}
        loading="lazy"
        onError={() => {
          markPhotoMissing(playerCode);
          setFailedFor(playerCode);
        }}
        src={getPlayerPhotoUrl(playerCode)}
        width={WIDTH}
      />
    </span>
  );
}
