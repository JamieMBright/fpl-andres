import { Navigate, useParams } from "react-router-dom";

import { parseTeamId } from "../public-ids";

/**
 * `/team/:id` was its own analysis page. Everything it showed now lives on the
 * plan, so the route survives only to keep old links and bookmarks working
 * rather than answering them with a 404.
 */
export default function TeamRedirect() {
  const { teamId } = useParams();
  const entryId = parseTeamId(teamId);
  return (
    <Navigate
      replace
      to={entryId === null ? "/" : `/plan?team=${String(entryId)}`}
    />
  );
}
