import { Link } from "react-router-dom";

import { money } from "../format";
import { readDeclaredSquad } from "../state/declared-squad";
import {
  PLAYERS_BY_ELEMENT_ID,
  type SolverPlayer,
} from "../state/season-solver";

/**
 * The fifteen you locked in, and a way back to change it.
 *
 * Before the first deadline the plan is solved from a squad you declared on
 * another page. Showing the plan without saying which fifteen it started from
 * is asking a reader to trust an input they cannot see, and leaving no route
 * back means a squad typed once is a squad you are stuck with.
 */
export function DeclaredSquadNote({ entryId }: { entryId: number }) {
  const declared = readDeclaredSquad(window.localStorage, entryId, 1);
  if (!declared) return null;

  const players = declared.elementIds
    .map((id) => PLAYERS_BY_ELEMENT_ID.get(id))
    .filter((player): player is SolverPlayer => player !== undefined);
  const spent = players.reduce(
    (total, player) => total + player.priceTenths,
    0,
  );

  return (
    <p className="declared-note">
      <strong>Planning from your own fifteen.</strong> Locked in{" "}
      {declared.declaredAt.slice(0, 10)}
      {players.length === declared.elementIds.length
        ? ` · ${money.format(spent / 10)}m spent`
        : ` · ${String(players.length)} of ${String(declared.elementIds.length)} rated`}
      . <Link to={`/team/${String(entryId)}`}>Change these fifteen</Link>.
    </p>
  );
}
