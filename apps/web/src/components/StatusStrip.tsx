import openingSquad from "../data/opening-squad.json";
import { captureDay } from "../format";
import {
  OPENING_SQUAD_SCHEMA_VERSION,
  requireArtifactVersion,
} from "../state/artifact-version";
import { projectionSeason } from "../state/projection-meta";

requireArtifactVersion(
  "opening-squad.json",
  openingSquad,
  OPENING_SQUAD_SCHEMA_VERSION,
);

// Read once at module load. Rendering must stay pure, and a countdown in days
// has no reason to tick during a session.
const LOADED_AT = Date.now();

const { consideredPlayers, withoutRecord, unavailable, bitPart } =
  openingSquad as {
    consideredPlayers: number;
    withoutRecord: number;
    unavailable: number;
    bitPart: number;
  };

const inTheGame = consideredPlayers + withoutRecord + unavailable + bitPart;

const dayFormatter = captureDay;

/**
 * The status strip, carrying facts rather than slogans.
 *
 * It previously listed four capability names, two of which are not built. A
 * strip that names features the site does not have is an advertisement, and a
 * decorative one nobody can read is worse than none.
 */
export function StatusStrip({ deadline }: { deadline: string }) {
  const kickoff = new Date(deadline);
  const days = Math.max(
    0,
    Math.ceil((kickoff.getTime() - LOADED_AT) / 86_400_000),
  );

  const cells = [
    `GW1 ${dayFormatter.format(kickoff)}`,
    days === 0 ? "DEADLINE PASSED" : `${days} DAYS`,
    `${inTheGame} PLAYERS`,
    `${consideredPlayers} SELECTABLE`,
    `${unavailable} FLAGGED`,
    `${projectionSeason} BASIS`,
  ];

  return (
    <div className="teletext-strip" role="status" aria-label="Current state">
      {cells.map((cell) => (
        <span key={cell}>{cell}</span>
      ))}
    </div>
  );
}
