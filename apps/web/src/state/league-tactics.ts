import type { LeagueExposure, Standing } from "./mini-league";

/**
 * What to do about the league, given where you sit in it.
 *
 * Ownership is a risk setting, not a return setting. Buying a player raises
 * your expected points by his whole projection whether or not your rivals own
 * him -- what their owning him changes is the *spread* of where you finish, not
 * the middle of it. Matching the field narrows that spread and taking what the
 * field has not got widens it.
 *
 * Which of those you want is decided by one thing: whether you are ahead. A
 * leader wants a narrow spread, because the middle already wins and variance
 * can only take it away. Somebody last wants a wide one, because the middle
 * loses and only an unusual week changes that. Nothing here says a player is
 * better; it says which kind of mistake you can afford.
 */

export type Posture = "cover" | "level" | "differ";

/**
 * Where the top of the table stops being catchable by playing the same team.
 *
 * A third of the way up is not a rule of thumb about football, it is the point
 * at which matching the field can still win: from there the leader is a bad
 * week away. Below it, copying is a decision to finish where you already are.
 */
const COVER_SHARE = 1 / 3;

export function postureFor(standing: Standing | null): Posture {
  if (!standing || standing.size < 2) return "level";
  const share = (standing.place - 1) / (standing.size - 1);
  if (share <= COVER_SHARE) return "cover";
  if (share >= 1 - COVER_SHARE) return "differ";
  return "level";
}

export const POSTURE_HEADINGS: Record<Posture, string> = {
  cover: "You are ahead. Narrow the spread.",
  level: "You are in the middle. Neither extreme pays.",
  differ: "You are behind. The middle will not catch them.",
};

export function postureVerdict(
  posture: Posture,
  standing: Standing | null,
): string {
  const place =
    standing === null
      ? "You are not in the squads that were read"
      : `${ordinal(standing.place)} of ${String(standing.size)}`;

  if (posture === "cover") {
    return (
      `${place}, and ${standing?.pointsAheadOfNext === null ? "nobody is behind you" : `${String(standing?.pointsAheadOfNext ?? 0)} points clear of the next one`}. ` +
      "Owning what they own means their good weeks are your good weeks, and " +
      "a lead survives an ordinary month. The names below that you do not " +
      "hold are the ones that can take it away in a single afternoon."
    );
  }
  if (posture === "differ") {
    return (
      `${place}, ${String(standing?.pointsBehindLeader ?? 0)} points off the top. ` +
      "Fielding the same eleven as the leader keeps the gap exactly where it " +
      "is. Something they have not got has to come off, and the shorter the " +
      "bar on the second board, the more one of his hauls is worth."
    );
  }
  return (
    `${place}. Copying the top concedes the places above you and going ` +
    "contrarian risks the ones below. Take the highest projection and let " +
    "the ownership decide only where two players are close."
  );
}

/**
 * What a chip is worth against these squads rather than against the game.
 *
 * A Triple Captain on a name half the league has already captained is a third
 * copy of a score most of them are getting twice; the same chip on a name none
 * of them own is the largest single swing in the game. That difference does not
 * appear anywhere in a projection, which is why it is said here.
 */
export function chipNote(
  posture: Posture,
  captaincy: readonly LeagueExposure[],
): string {
  const crowded = captaincy.filter((row) => row.captainedShare >= 0.5);
  if (crowded.length > 0) {
    return posture === "differ"
      ? "Half this league is captaining the same player. A Triple Captain on him buys you a third copy of a score they are all already getting twice — it moves the whole table up and you with it. Played on somebody they have not got, it is the biggest single swing available to you."
      : "Half this league is captaining the same player. A Triple Captain on him is the safe version: it cannot lose you ground, and it cannot gain much either.";
  }
  return posture === "cover"
    ? "No captain is crowded here, so a Bench Boost is the quieter chip: it adds points without betting on one afternoon, which is what a lead wants."
    : "No captain is crowded here, so the armband is already doing differentiating work. A Triple Captain is worth more than a Bench Boost while you are chasing.";
}

function ordinal(place: number): string {
  const last = place % 10;
  const teen = place % 100;
  if (teen >= 11 && teen <= 13) return `${String(place)}th`;
  if (last === 1) return `${String(place)}st`;
  if (last === 2) return `${String(place)}nd`;
  if (last === 3) return `${String(place)}rd`;
  return `${String(place)}th`;
}
