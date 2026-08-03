import { useState } from "react";

import { kitForShortName } from "../kit/team-kits";
import {
  getPlayerPhotoUrl,
  isPhotoKnownMissing,
  markPhotoMissing,
} from "../kit/player-photo";
import { CeefaxShirt } from "./CeefaxShirt";

/**
 * A player headshot, or his club shirt when there is not one.
 *
 * The shirt beats a generic silhouette because it still says something true:
 * who he plays for, and which number he wears. A silhouette says only that we
 * failed to load an image.
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

export interface PlayerAvatarProps {
  /** FPL element code. Stable across seasons, unlike the element id. */
  playerCode: number | null | undefined;
  /** The player's name, for the accessible name. */
  name: string;
  /** Club short name, so the fallback can wear the right shirt. */
  club?: string | null;
  squadNumber?: number | null;
  className?: string;
}

export function PlayerAvatar({
  playerCode,
  name,
  club,
  squadNumber = null,
  className,
}: PlayerAvatarProps) {
  const usable = typeof playerCode === "number" && playerCode > 0;
  // Remembering *which* player failed rather than *that* one did means a
  // different player in the same slot retries instead of inheriting the miss.
  const [failedFor, setFailedFor] = useState<number | null>(null);
  const failed =
    !usable || failedFor === playerCode || isPhotoKnownMissing(playerCode);

  const wrapper = className ? `player-avatar ${className}` : "player-avatar";

  if (failed) {
    const kit = kitForShortName(club);
    return (
      <span className={`${wrapper} player-avatar-empty`}>
        {kit ? (
          <CeefaxShirt
            className="player-avatar-shirt"
            kit={kit}
            label={`${name}, no photograph — ${kit.name} shirt`}
            squadNumber={squadNumber}
          />
        ) : (
          <span
            className="player-avatar-unknown"
            role="img"
            aria-label={`${name}, no photograph`}
          >
            ?
          </span>
        )}
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
