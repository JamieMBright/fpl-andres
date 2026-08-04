import { useId, useMemo, useState } from "react";

import type { AnalysisPlayer } from "../state/analysis-pool";

/**
 * Pick who to highlight, by name or by club, one at a time.
 *
 * A free-text box asked the reader to guess the spelling the data uses. Typing
 * "Leeds United" matched nothing because the pool holds "LEE", and nothing on
 * screen said so. This offers what actually exists and adds it as a chip, so a
 * miss is impossible and a shortlist can hold more than one thing at once.
 */

const MAX_SUGGESTIONS = 8;

export interface HighlightPickerProps {
  players: readonly AnalysisPlayer[];
  /** Player codes and club short names, mixed, as chosen so far. */
  highlights: readonly string[];
  onChange: (next: string[]) => void;
}

/** Fold accents so "saliba" finds "Salibá". */
function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

interface Suggestion {
  /** What goes in the URL: a club short name, or `#` and a player code. */
  token: string;
  label: string;
  detail: string;
}

export function HighlightPicker({
  players,
  highlights,
  onChange,
}: HighlightPickerProps) {
  const ids = useId();
  const [typed, setTyped] = useState("");

  const clubs = useMemo(
    () => [...new Set(players.map((player) => player.club))].sort(),
    [players],
  );

  const suggestions = useMemo<Suggestion[]>(() => {
    const needle = fold(typed.trim());
    if (needle.length < 2) return [];

    const clubHits = clubs
      .filter((club) => fold(club).includes(needle))
      .map<Suggestion>((club) => ({
        token: club,
        label: club,
        detail: "every player at this club",
      }));

    const playerHits = players
      .filter((player) => fold(player.name).includes(needle))
      .slice(0, MAX_SUGGESTIONS)
      .map<Suggestion>((player) => ({
        token: `#${String(player.code)}`,
        label: player.name,
        detail: `${player.position} · ${player.club}`,
      }));

    return [...clubHits, ...playerHits]
      .filter((entry) => !highlights.includes(entry.token))
      .slice(0, MAX_SUGGESTIONS);
  }, [typed, clubs, players, highlights]);

  const labelOf = (token: string): string => {
    if (!token.startsWith("#")) return token;
    const code = Number(token.slice(1));
    return players.find((player) => player.code === code)?.name ?? token;
  };

  const add = (token: string) => {
    setTyped("");
    if (!highlights.includes(token)) onChange([...highlights, token]);
  };

  return (
    <div className="highlight-picker">
      {highlights.length > 0 ? (
        <ul className="highlight-chips">
          {highlights.map((token) => (
            <li key={token}>
              <span translate="no">{labelOf(token)}</span>
              <button
                aria-label={`Stop highlighting ${labelOf(token)}`}
                onClick={() => {
                  onChange(highlights.filter((entry) => entry !== token));
                }}
                type="button"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <label htmlFor={`${ids}-search`}>Highlight players</label>
      <input
        aria-autocomplete="list"
        aria-controls={`${ids}-suggestions`}
        aria-expanded={suggestions.length > 0}
        autoComplete="off"
        id={`${ids}-search`}
        onChange={(event) => {
          setTyped(event.target.value);
        }}
        onKeyDown={(event) => {
          // Enter takes the first suggestion, which is what a reader who has
          // typed enough to see one expects it to do.
          const first = suggestions[0];
          if (event.key === "Enter" && first) {
            event.preventDefault();
            add(first.token);
          }
        }}
        placeholder="Start typing a name or club"
        role="combobox"
        type="text"
        value={typed}
      />

      {suggestions.length > 0 ? (
        <ul className="highlight-suggestions" id={`${ids}-suggestions`}>
          {suggestions.map((entry) => (
            <li key={entry.token}>
              <button
                onClick={() => {
                  add(entry.token);
                }}
                type="button"
              >
                <span translate="no">{entry.label}</span>
                <span className="highlight-detail">{entry.detail}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {typed.trim().length >= 2 && suggestions.length === 0 ? (
        <p className="scatter-hint">
          Nothing in the plotted pool matches that. Widen the filters and try
          again.
        </p>
      ) : null}
    </div>
  );
}
