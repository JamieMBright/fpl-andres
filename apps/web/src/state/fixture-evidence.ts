import inputs from "../data/season-inputs.json";

export interface FixtureAdjustments {
  attacking: number;
  cleanSheet: number;
  conceding: number;
  saves: number;
  defensiveContribution: number;
}

export interface FixtureEvidence {
  event: number;
  opponent: string;
  venue: "H" | "A";
  kickoff: string | null;
  expectedGoals: number;
  opponentExpectedGoals: number;
  cleanSheetProbability: number;
  adjustments: FixtureAdjustments;
  difficulty: {
    raw: number | null;
    summary: number | null;
    clipped: boolean;
  };
  source: string;
  updatedAt: string | null;
  level: string;
}

type PublishedFixtureEvidence = Omit<
  FixtureEvidence,
  "source" | "updatedAt" | "level"
>;

const published = (
  inputs as unknown as {
    fixtureEvidence: {
      source: string;
      updatedAt: string | null;
      level: string;
      byClub: Record<string, PublishedFixtureEvidence[]>;
    };
  }
).fixtureEvidence;

export function fixtureEvidenceForEvent(
  club: string,
  event: number,
): FixtureEvidence[] {
  return (published.byClub[club] ?? [])
    .filter((entry) => entry.event === event)
    .map((entry) => ({
      ...entry,
      source: published.source,
      updatedAt: published.updatedAt,
      level: published.level,
    }));
}

export function fixtureEvidenceAt(
  club: string,
  eventIndex: number,
): FixtureEvidence | null {
  const event = inputs.events[eventIndex];
  return event === undefined
    ? null
    : (fixtureEvidenceForEvent(club, event)[0] ?? null);
}

export function fixtureEvidenceForClubs(
  clubs: Iterable<string>,
  event: number,
): Record<string, FixtureEvidence[]> {
  return Object.fromEntries(
    [...new Set(clubs)].flatMap((club) => {
      const evidence = fixtureEvidenceForEvent(club, event);
      return evidence.length === 0 ? [] : [[club, evidence]];
    }),
  );
}
