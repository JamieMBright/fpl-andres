import { useState } from "react";

import {
  OBJECTIVES,
  OBJECTIVE_NAMES,
  readRankObjective,
  saveRankObjective,
  type Objective,
  type RankObjective,
} from "../state/rank-objective";
import { InfoMarker } from "./InfoMarker";

/**
 * Which race, asked before anything is recommended.
 *
 * Two managers with identical squads want opposite advice depending on this,
 * and nothing in the public data says which one you are. Guessing would give
 * half the readers the wrong plan with no way to tell it was the wrong
 * question rather than a wrong number.
 */
export function RankObjectiveForm({
  entryId,
  onChosen,
}: {
  entryId: number;
  onChosen: (chosen: RankObjective) => void;
}) {
  const [chosen, setChosen] = useState<RankObjective | null>(() =>
    readRankObjective(window.localStorage, entryId),
  );
  const [league, setLeague] = useState(() =>
    chosen?.leagueId === null || chosen?.leagueId === undefined
      ? ""
      : String(chosen.leagueId),
  );

  function commit(next: RankObjective) {
    const saved = saveRankObjective(window.localStorage, entryId, next);
    setChosen(saved);
    onChosen(saved);
  }

  function pick(objective: Objective) {
    commit({
      objective,
      leagueId: objective === "league" ? Number(league) || null : null,
    });
  }

  return (
    <form
      aria-labelledby="rank-objective"
      className="rank-objective"
      onSubmit={(event) => {
        event.preventDefault();
        commit({ objective: "league", leagueId: Number(league) || null });
      }}
    >
      <h3 id="rank-objective">Which race matters?</h3>
      <p>
        Overall rank rewards expected points. A mini-league also cares about
        what the managers around you own.
        <InfoMarker label="why the answer changes the plan">
          Overall rank is a race against eleven million squads, so nobody
          else&rsquo;s team is readable and the best you can do is take the
          highest expected points on offer. A mini-league is a race against a
          dozen squads you can read one by one, and there the spread matters
          more than the average: a player nine of your twelve rivals start costs
          you nine places when he hauls, whatever his projection says.
        </InfoMarker>
      </p>

      <fieldset className="rank-objective-choice">
        <legend>Chasing</legend>
        {OBJECTIVES.map((objective) => (
          <label key={objective}>
            <input
              checked={chosen?.objective === objective}
              name="rank-objective-choice"
              onChange={() => {
                pick(objective);
              }}
              type="radio"
              value={objective}
            />
            {OBJECTIVE_NAMES[objective]}
          </label>
        ))}
      </fieldset>

      {chosen?.objective === "league" ? (
        <div className="rank-objective-league">
          <label htmlFor="league-id">League ID</label>
          <div className="input-command">
            <input
              autoComplete="off"
              id="league-id"
              inputMode="numeric"
              maxLength={10}
              onChange={(event) => {
                setLeague(event.target.value.replace(/\D/g, ""));
              }}
              placeholder="e.g. 34555"
              value={league}
            />
            <button type="submit">Read this league</button>
          </div>
          <p className="field-hint">
            Open the league on the FPL site. The number after{" "}
            <span className="mono">/leagues/</span> in the address bar is the
            League ID. Classic leagues only.
          </p>
        </div>
      ) : null}
    </form>
  );
}
